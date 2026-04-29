"""
voice.py — Complete Voice Interaction API (Phase 2)
Endpoints:
  POST /voice/transcribe  — Audio → text via Whisper
  POST /voice/ask         — Ask about a document verbally
  GET  /voice/tts         — Text → speech (streaming)
  GET  /voice/status      — Check voice feature availability
"""
from __future__ import annotations
import io
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_TYPES = {
    "audio/mpeg", "audio/mp4", "audio/wav", "audio/webm",
    "audio/ogg", "audio/m4a", "audio/x-m4a",
}

class AskRequest(BaseModel):
    document_id: int | None = None
    question: str
    language: str = "en"

class TranscribeResponse(BaseModel):
    text: str
    language: str | None = None
    duration: float | None = None

class AskResponse(BaseModel):
    question: str
    answer: str
    document_id: int | None = None
    tts_available: bool

@router.get("/status")
def voice_status(current_user: User = Depends(get_current_user)):
    return {
        "voice_enabled": bool(settings.OPENAI_API_KEY),
        "stt_provider": "openai_whisper" if settings.OPENAI_API_KEY else "unavailable",
        "tts_provider": "openai_tts" if settings.OPENAI_API_KEY else "unavailable",
        "supported_languages": ["en", "es", "zh", "hi", "fr", "de", "it", "pt"],
        "message": "Voice features active" if settings.OPENAI_API_KEY else "Set OPENAI_API_KEY to enable voice"
    }

@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = "en",
    current_user: User = Depends(get_current_user),
):
    """Convert uploaded audio to text using OpenAI Whisper."""
    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="Voice features not configured. Set OPENAI_API_KEY.")

    if file.content_type not in SUPPORTED_AUDIO_TYPES and not file.filename.endswith(
        (".mp3", ".mp4", ".wav", ".webm", ".ogg", ".m4a")
    ):
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {file.content_type}")

    content = await file.read()
    if len(content) > 25 * 1024 * 1024:  # 25MB Whisper limit
        raise HTTPException(status_code=413, detail="Audio file too large. Maximum 25MB.")

    try:
        import openai
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        audio_file = io.BytesIO(content)
        audio_file.name = file.filename or "audio.wav"

        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language=language if language != "en" else None,
            response_format="verbose_json",
        )

        return TranscribeResponse(
            text=result.text.strip(),
            language=getattr(result, "language", language),
            duration=getattr(result, "duration", None),
        )
    except Exception as e:
        logger.error("Whisper transcription failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Transcription failed: {str(e)}")


@router.post("/ask", response_model=AskResponse)
async def ask_about_document(
    payload: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Answer a voice question about a document using Claude."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="AI features not configured.")

    # Get document context if provided
    context = ""
    if payload.document_id:
        from app.models.document import Document
        from app.services.document_access_service import DocumentAccessService
        access = DocumentAccessService()
        doc = db.get(Document, payload.document_id)
        if doc:
            try:
                access.assert_can_view(db, doc, current_user)
                context = f"""
Document: {doc.name}
Type: {doc.document_type}
Summary: {doc.summary or 'Not yet analyzed'}
Key fields: {doc.extracted_fields or {}}
Deadlines: {doc.deadlines or []}
"""
            except Exception:
                pass  # Don't fail if access check fails

    # Build senior-friendly prompt
    system_prompt = """You are a compassionate AI assistant helping a senior understand their paperwork.
Answer clearly and simply in 1-3 sentences. No jargon. Be reassuring and helpful.
If you don't know something, say so honestly. Never make up facts.
Always suggest consulting a doctor, pharmacist, or trusted person for medical decisions."""

    user_message = f"""Question: {payload.question}

{f'Document context:{context}' if context else 'No specific document provided.'}

Please answer in simple language a senior can understand."""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=300,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        answer = response.content[0].text.strip()
    except Exception as e:
        logger.error("Claude voice response failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not generate answer. Please try again.")

    return AskResponse(
        question=payload.question,
        answer=answer,
        document_id=payload.document_id,
        tts_available=bool(settings.OPENAI_API_KEY),
    )


@router.get("/tts")
async def text_to_speech(
    text: str,
    voice: str = "nova",  # nova is warm and clear — best for seniors
    current_user: User = Depends(get_current_user),
):
    """Convert text to speech audio (streaming MP3)."""
    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="TTS not configured.")

    if len(text) > 4096:
        text = text[:4096]

    if voice not in ("alloy", "echo", "fable", "onyx", "nova", "shimmer"):
        voice = "nova"

    try:
        import openai
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
            response_format="mp3",
            speed=0.9,  # Slightly slower for seniors
        )
        audio_bytes = response.content

        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=response.mp3",
                "Content-Length": str(len(audio_bytes)),
                "Cache-Control": "no-cache",
            },
        )
    except Exception as e:
        logger.error("TTS failed: %s", e)
        raise HTTPException(status_code=502, detail=f"TTS failed: {str(e)}")
