from __future__ import annotations

import json
import re
from datetime import datetime

from openai import OpenAI

from app.core.config import settings

PROMPT = """You are a helpful paperwork assistant for families and seniors.
Return JSON with keys:
- summary: plain-English summary of the document
- deadlines: array of objects with keys title, date, reason, action
Only include deadlines that are explicitly stated or strongly implied.
"""

DATE_PATTERNS = [
    r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
    r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+\d{4}\b',
]


def _fallback_deadlines(text: str) -> list[dict]:
    dates: list[str] = []
    for pattern in DATE_PATTERNS:
        dates.extend(re.findall(pattern, text, flags=re.IGNORECASE))
    unique_dates = list(dict.fromkeys(dates))[:5]
    results = []
    for raw_date in unique_dates:
        results.append(
            {
                'title': f'Important date found: {raw_date}',
                'date': raw_date,
                'reason': 'Detected from the uploaded document',
                'action': 'Review the section around this date to confirm required next steps',
            }
        )
    return results


def summarize_text(text: str) -> dict:
    if settings.LLM_PROVIDER == 'openai' and settings.OPENAI_API_KEY:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {'role': 'system', 'content': PROMPT},
                {'role': 'user', 'content': text[:14000]},
            ],
            response_format={'type': 'json_object'},
        )
        content = response.choices[0].message.content or '{}'
        parsed = json.loads(content)
        parsed.setdefault('summary', 'No summary available.')
        parsed.setdefault('deadlines', [])
        return parsed

    excerpt = text[:900].strip().replace('\n', ' ')
    return {
        'summary': f'Plain-English summary: {excerpt[:400]}...' if excerpt else 'No summary available.',
        'deadlines': _fallback_deadlines(text),
        'generated_at': datetime.utcnow().isoformat(),
    }
