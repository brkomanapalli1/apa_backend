"""
voice.py — Voice Interaction API (Phase 2)

Endpoints:
  POST /voice/transcribe  — Convert audio to text (Whisper)
  POST /voice/ask         — Ask a question about a document verbally
  GET  /voice/tts         — Convert text response to speech
  GET  /voice/status      — Check if voice features are enabled
"""
from __future__ import annotations
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


@router.get("/status")
def voice_status(current_user: User = Depends(get_current_user)):
    """Check if voice features are available."""
    return {
        "voice_enabled": settings.voice_available,
        "stt_provider": "openai_whisper" if settings.WHISPER_API_KEY else "unavailable",
        "tts_provider": settings.TTS_PROVIDER,
        "message": (
            "Voice features are active." if settings.voice_available
            else "Voice features require WHISPER_API_KEY to be configured."
        ),
    }


@router.post("/transcribe")
async def transcribe_audio(
    audio_file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Transcribe audio to text using OpenAI Whisper.
    Accepts: mp3, mp4, mpeg, mpga, m4a, wav, webm
    Max size: 25MB
    """
    if not settings.voice_available:
        raise HTTPException(
            status_code=503,
            detail="Voice features are not enabled. Please configure WHISPER_API_KEY.",
        )

    MAX_AUDIO_SIZE = 25 * 1024 * 1024
    content = await audio_file.read()
    if len(content) > MAX_AUDIO_SIZE:
        raise HTTPException(status_code=400, detail="Audio file too large. Maximum 25MB.")

    allowed_types = {"audio/mpeg", "audio/mp4", "audio/wav", "audio/webm", "audio/m4a"}
    if audio_file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Unsupported audio format: {audio_file.content_type}")

    try:
        import openai
        client = openai.OpenAI(api_key=settings.WHISPER_API_KEY)

        import io
        audio_bytes = io.BytesIO(content)
        audio_bytes.name = audio_file.filename or "audio.mp3"

        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_bytes,
            response_format="text",
        )
        return {"transcript": str(transcript), "language": "en"}

    except Exception as exc:
        logger.error("Transcription failed: %s", exc)
        raise HTTPException(status_code=500, detail="Transcription failed. Please try again.")


class VoiceAskRequest(BaseModel):
    question: str
    document_id: int | None = None


@router.post("/ask")
async def voice_ask(
    payload: VoiceAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Answer a voice question about a document.
    Accepts transcribed text, returns plain-English answer suitable for TTS.

    Example questions:
      "What does this letter mean?"
      "Do I need to pay this bill?"
      "When is the deadline?"
      "What medications should I take today?"
    """
    if not payload.question or len(payload.question.strip()) < 3:
        raise HTTPException(status_code=400, detail="Question is too short.")

    context = ""

    if payload.document_id:
        from app.models.document import Document
        doc = db.query(Document).filter(
            Document.id == payload.document_id,
            Document.owner_id == current_user.id,
        ).first()
        if doc:
            fields = doc.extracted_fields or {}
            ui = fields.get("ui_summary", {})
            context = f"""
Document: {doc.name}
Type: {doc.document_type}
Summary: {doc.summary or 'Not available'}
Payment status: {ui.get('payment_message', 'Unknown')}
Key date: {ui.get('main_due_date', 'None found')}
Amount: {ui.get('main_amount', 'None found')}
"""

    # Use LLM to answer
    from app.services.llm_service import analyze_document_with_llm
    from app.core.config import settings as s

    # Build a simple Q&A prompt
    prompt = f"""You are a helpful assistant for seniors. Answer this question clearly and briefly, as if speaking aloud.
Keep the answer under 3 sentences. Use plain English, no jargon.

{f'Document context:{context}' if context else ''}

Question: {payload.question}

Answer:"""

    try:
        if s.effective_llm_provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=s.ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model=s.ANTHROPIC_MODEL,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = msg.content[0].text.strip()
        elif s.effective_llm_provider == "openai":
            import openai
            client = openai.OpenAI(api_key=s.OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model=s.OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            answer = resp.choices[0].message.content.strip()
        else:
            # Mock response using document summary
            if context and "Summary:" in context:
                summary_line = [l for l in context.split("\n") if "Summary:" in l]
                answer = summary_line[0].replace("Summary:", "").strip() if summary_line else "I cannot answer without AI configured."
            else:
                answer = "AI features are not configured. Please set up your API key to enable voice answers."
    except Exception as exc:
        logger.error("Voice answer failed: %s", exc)
        answer = "I'm sorry, I wasn't able to answer that question right now. Please try again."

    return {
        "question": payload.question,
        "answer": answer,
        "document_id": payload.document_id,
    }


@router.get("/tts")
async def text_to_speech(
    text: str,
    current_user: User = Depends(get_current_user),
):
    """
    Convert text to speech audio.
    Returns audio/mpeg stream.
    Uses OpenAI TTS or Azure Speech depending on configuration.
    """
    if settings.TTS_PROVIDER == "disabled":
        raise HTTPException(status_code=503, detail="Text-to-speech is not enabled.")

    if not text or len(text.strip()) < 2:
        raise HTTPException(status_code=400, detail="Text is too short.")

    # Limit TTS text length
    text = text[:500]

    try:
        if settings.TTS_PROVIDER == "openai" and settings.WHISPER_API_KEY:
            import openai
            client = openai.OpenAI(api_key=settings.WHISPER_API_KEY)
            response = client.audio.speech.create(
                model="tts-1",
                voice="nova",  # Clear, friendly voice
                input=text,
            )

            import io
            audio_data = io.BytesIO(response.content)
            return StreamingResponse(audio_data, media_type="audio/mpeg")

        elif settings.TTS_PROVIDER == "azure" and settings.AZURE_SPEECH_KEY:
            # Azure Cognitive Services TTS
            import azure.cognitiveservices.speech as speechsdk
            speech_config = speechsdk.SpeechConfig(
                subscription=settings.AZURE_SPEECH_KEY,
                region=settings.AZURE_SPEECH_REGION,
            )
            speech_config.speech_synthesis_voice_name = "en-US-JennyNeural"
            synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)
            result = synthesizer.speak_text_async(text).get()
            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                import io
                return StreamingResponse(io.BytesIO(result.audio_data), media_type="audio/wav")
            raise HTTPException(status_code=500, detail="TTS synthesis failed.")

    except Exception as exc:
        logger.error("TTS failed: %s", exc)
        raise HTTPException(status_code=500, detail="Text-to-speech failed.")

    raise HTTPException(status_code=503, detail="No TTS provider configured.")
