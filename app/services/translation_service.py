"""
translation_service.py — Multilingual Document Support (Phase 5)

Translates summaries, deadlines, and recommendations into the user's
preferred language using Claude.

Supported: Spanish, Chinese (Simplified), Hindi, French, German, Italian,
           Portuguese, Korean, Japanese, Vietnamese, Tagalog, Arabic
"""
from __future__ import annotations
import logging
from typing import Any
from app.core.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "zh": "Chinese (Simplified)",
    "hi": "Hindi",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ko": "Korean",
    "ja": "Japanese",
    "vi": "Vietnamese",
    "tl": "Tagalog (Filipino)",
    "ar": "Arabic",
}


def translate_document_analysis(
    analysis: dict[str, Any],
    target_language: str,
) -> dict[str, Any]:
    """
    Translate summary, deadlines, and recommendations to target language.
    Preserves all other fields (amounts, dates, IDs) unchanged.
    Returns modified analysis dict.
    """
    if target_language == "en" or target_language not in SUPPORTED_LANGUAGES:
        return analysis

    lang_name = SUPPORTED_LANGUAGES[target_language]

    # Build translation payload — only translate human-readable text
    to_translate = {
        "summary": analysis.get("summary", ""),
        "deadlines": [
            {
                "title": d.get("title", ""),
                "reason": d.get("reason", ""),
                "action": d.get("action", ""),
            }
            for d in (analysis.get("deadlines") or [])
        ],
        "recommendations": [
            {
                "title": r.get("title", ""),
                "why": r.get("why", ""),
                "action": r.get("action", ""),
            }
            for r in (analysis.get("recommendations") or [])
        ],
    }

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = f"""Translate the following JSON content to {lang_name}.
Keep all JSON keys in English. Only translate the string values.
Keep dates, amounts, account numbers, and proper nouns unchanged.
Use simple, clear language suitable for an elderly person.
Return ONLY valid JSON with no markdown fences.

{__import__('json').dumps(to_translate, ensure_ascii=False, indent=2)}"""

        response = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        import json
        translated = json.loads(response.content[0].text.strip())

        # Merge back — only replace text fields
        result = dict(analysis)
        result["summary"] = translated.get("summary", analysis.get("summary", ""))

        # Merge deadline translations
        orig_deadlines = analysis.get("deadlines") or []
        trans_deadlines = translated.get("deadlines") or []
        merged_deadlines = []
        for i, orig in enumerate(orig_deadlines):
            trans = trans_deadlines[i] if i < len(trans_deadlines) else {}
            merged_deadlines.append({
                **orig,
                "title": trans.get("title", orig.get("title", "")),
                "reason": trans.get("reason", orig.get("reason", "")),
                "action": trans.get("action", orig.get("action", "")),
            })
        result["deadlines"] = merged_deadlines

        # Merge recommendation translations
        orig_recs = analysis.get("recommendations") or []
        trans_recs = translated.get("recommendations") or []
        merged_recs = []
        for i, orig in enumerate(orig_recs):
            trans = trans_recs[i] if i < len(trans_recs) else {}
            merged_recs.append({
                **orig,
                "title": trans.get("title", orig.get("title", "")),
                "why": trans.get("why", orig.get("why", "")),
                "action": trans.get("action", orig.get("action", "")),
            })
        result["recommendations"] = merged_recs
        result["language"] = target_language

        return result

    except Exception as e:
        logger.warning("Translation failed for %s: %s — returning English", target_language, e)
        return analysis


def get_supported_languages() -> dict[str, str]:
    return SUPPORTED_LANGUAGES
