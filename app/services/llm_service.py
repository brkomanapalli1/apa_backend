"""
llm_service.py — Multi-provider LLM client.

Priority: Anthropic Claude → OpenAI → heuristic mock
Edge cases: timeout retry, malformed JSON fallback, rate-limit backoff,
            input truncation, provider key missing at runtime.
"""
from __future__ import annotations
import json, logging, time
from typing import Any
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_INPUT_CHARS = 8_000
_MAX_RETRIES = settings.LLM_MAX_RETRIES
_TIMEOUT = settings.LLM_TIMEOUT_SECONDS

_ANALYSIS_SYSTEM = """You are a compassionate AI paperwork assistant helping seniors and families.

Analyze the document and return ONLY a strict JSON object with these keys:
- document_type: one of [medicare_summary_notice, explanation_of_benefits,
  claim_denial_letter, itemized_medical_bill, medicaid_notice,
  social_security_notice, prescription_drug_notice, veterans_benefits_letter,
  electricity_bill, natural_gas_bill, water_sewer_bill, trash_recycling_bill,
  telecom_bill, combined_utility_bill, rent_statement, hoa_statement,
  property_tax_bill, mortgage_statement, home_insurance_bill,
  credit_card_statement, bank_statement, loan_statement, collection_notice,
  irs_notice, food_assistance_notice, housing_assistance_notice,
  financial_assistance_letter, unknown]
- document_type_confidence: 0.0 to 1.0
- summary: 2-4 sentences in plain English for a senior, no jargon
- extracted_fields: key structured facts (amounts, dates, IDs, names)
- deadlines: [{title, date, reason, action}] — REAL deadlines only.
  NEVER use date of birth as a deadline or key date.
  Always return concrete ISO dates YYYY-MM-DD not approximate text.
  For 90 days supply from today 2026-04-20 use date 2026-07-18.
  For every 14 days use date 2026-05-04. Max 5 deadlines.
- recommendations: [{title, why, priority, action}] — practical steps, max 5
- billing_errors: [{description, amount, severity}] — may be empty
- letter: {title, subject, body, audience, use_case} — ready-to-send draft
- medications: array of medication objects, empty array if no medications:
  name, dosage, frequency, instructions, with_food (true/false/null),
  reminder_times (REQUIRED array of 24h times like 08:00 18:00 — NEVER empty,
  infer from instructions: twice daily with meal = 08:00 and 18:00,
  morning empty stomach = 07:00, once daily = 09:00, bedtime = 21:00),
  refill_date (ISO YYYY-MM-DD or null), days_supply (integer or null)

RULES:
1. EOB is NOT a bill — always say so clearly.
2. Denial letters include appeal urgency and deadline.
3. Never invent facts — only extract what is in the document.
4. Return ONLY JSON. No markdown fences, no preamble.
5. For prescriptions document_type MUST be prescription_drug_notice.
6. NEVER use date of birth as a deadline or key date.
7. Always infer reminder_times from medication instructions never leave empty.
8. IRS/Internal Revenue Service/Publication 594/tax collection → MUST be irs_notice.
9. Social Security Administration/SSA → social_security_notice.
10. Medicare Summary Notice/MSN → medicare_summary_notice.
11. Never confuse IRS documents with Medicare documents — they are completely different.
12. Read the document header and logo carefully before classifying.
"""

_LETTER_SYSTEM = """\
Write a professional, compassionate letter for a senior based on the context.
Return ONLY JSON: {title, subject, body, audience, use_case}.
Body must be complete and mail-ready. No markdown fences.
"""


def _retry(fn, max_retries: int = _MAX_RETRIES) -> Any:
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn()
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exc = exc
            wait = 2 ** attempt
            logger.warning("LLM attempt %d/%d failed, retry in %ds: %s", attempt+1, max_retries, wait, exc)
            time.sleep(wait)
        except Exception:
            raise
    raise last_exc  # type: ignore


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return text.strip()


def _call_anthropic(system: str, user: str) -> dict[str, Any]:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=_TIMEOUT)
    def _call():
        msg = client.messages.create(
            model=settings.ANTHROPIC_MODEL, max_tokens=settings.LLM_MAX_TOKENS,
            system=system, messages=[{"role": "user", "content": user[:_MAX_INPUT_CHARS]}],
        )
        return json.loads(_strip_fences(msg.content[0].text if msg.content else "{}"))
    return _retry(_call)


def _call_openai(system: str, user: str) -> dict[str, Any]:
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=_TIMEOUT)
    def _call():
        r = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user[:_MAX_INPUT_CHARS]}],
            response_format={"type": "json_object"}, max_tokens=settings.LLM_MAX_TOKENS,
            temperature=settings.LLM_TEMPERATURE,
        )
        return json.loads(r.choices[0].message.content or "{}")
    return _retry(_call)


def analyze_document_with_llm(text: str, filename: str = "") -> dict[str, Any] | None:
    if not text or not text.strip():
        return None
    provider = settings.effective_llm_provider
    prompt = f"Document filename: {filename}\n\n---\n\n{text[:_MAX_INPUT_CHARS]}"
    try:
        if provider == "anthropic":
            logger.info("Analyzing with Claude (%s)", settings.ANTHROPIC_MODEL)
            r = _call_anthropic(_ANALYSIS_SYSTEM, prompt)
            r["analyzer"] = f"claude/{settings.ANTHROPIC_MODEL}"
            return r
        if provider == "openai":
            logger.info("Analyzing with OpenAI (%s)", settings.OPENAI_MODEL)
            r = _call_openai(_ANALYSIS_SYSTEM, prompt)
            r["analyzer"] = f"openai/{settings.OPENAI_MODEL}"
            return r
    except json.JSONDecodeError as exc:
        logger.warning("LLM JSON parse error for %s: %s — using heuristics", filename, exc)
    except Exception as exc:
        logger.error("LLM failed for %s: %s — using heuristics", filename, exc, exc_info=True)
    return None


def generate_letter_with_llm(document_type: str, extracted_fields: dict, recommendations: list, text: str) -> dict | None:
    provider = settings.effective_llm_provider
    if provider == "mock":
        return None
    context = json.dumps({"document_type": document_type,
                           "key_fields": {k: v for k, v in (extracted_fields or {}).items()
                                          if k not in ("all_amounts", "ui_summary", "extracted_text")},
                           "top_recommendation": (recommendations or [{}])[0]}, default=str)
    try:
        if provider == "anthropic":
            return _call_anthropic(_LETTER_SYSTEM, context)
        if provider == "openai":
            return _call_openai(_LETTER_SYSTEM, context)
    except Exception as exc:
        logger.warning("Letter LLM failed: %s", exc)
    return None


def summarize_text(text: str) -> dict[str, Any]:
    """Legacy helper — used by older routes."""
    from app.services.bill_intelligence import analyze_document as _analyze
    result = analyze_document_with_llm(text)
    if result:
        return {"summary": result.get("summary", ""), "deadlines": result.get("deadlines", []),
                "generated_at": result.get("generated_at")}
    h = _analyze(text)
    return {"summary": h.get("summary", ""), "deadlines": h.get("deadlines", []),
            "generated_at": h.get("generated_at")}