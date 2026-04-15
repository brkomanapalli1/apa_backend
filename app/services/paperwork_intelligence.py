"""
paperwork_intelligence.py — backward-compatibility shim.

All intelligence logic now lives in bill_intelligence.py, which supports:
  - All original medical types (Medicare, EOB, denial, itemized bill, Medicaid,
    Social Security, prescription drug, veterans benefits)
  - NEW: electricity, gas, water/sewer, telecom, trash bills
  - NEW: rent, HOA, property tax, mortgage, home insurance
  - NEW: credit card, collection notices, IRS notices, loans, SNAP, VA

This shim re-exports every name the rest of the codebase imports so that
document_service.py, documents.py route, and any other file continue to
work without modification.
"""
from __future__ import annotations
from typing import Any

from app.services.bill_intelligence import (  # noqa: F401
    analyze_document as analyze_phase1_document,
    analyze_document,
    build_letter,
    detect_document_type,
    extract_fields,
    build_summary,
    build_recommendations,
    build_deadlines,
    build_senior_view,
    build_payment_guidance,
    build_warning_flags,
    build_call_script,
    derive_document_family,
)


def generate_letter_for_document(
    document_type: str,
    extracted_fields: dict[str, Any] | None,
    recommendations: list[dict[str, str]] | None,
    text: str,
) -> dict[str, str]:
    """
    Signature-compatible wrapper used by document_service.py and the
    /generate-letter route. The original accepted recommendations + text;
    the new build_letter only needs type + fields.
    """
    return build_letter(document_type or "unknown", extracted_fields or {})
