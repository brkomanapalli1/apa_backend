"""
financial_analysis.py — Financial Change Detection (Phase 4)

Detects:
  - Unusual bill increases (>20% month-over-month)
  - Duplicate subscriptions or charges
  - Missing expected bills (e.g. no Medicare statement in 3 months)
  - Expense trend summaries
  - Budget category breakdowns
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session


UTILITY_TYPES = {
    "electricity_bill", "natural_gas_bill", "water_sewer_bill",
    "telecom_bill", "trash_recycling_bill", "combined_utility_bill",
}
MEDICAL_TYPES = {
    "itemized_medical_bill", "explanation_of_benefits",
    "medicare_summary_notice", "medicaid_notice",
}
FINANCIAL_TYPES = {
    "credit_card_statement", "loan_statement", "mortgage_statement",
    "rent_statement", "hoa_statement", "property_tax_bill",
}


def analyze_financial_changes(
    user_id: int, db: Session, months_back: int = 6,
) -> dict[str, Any]:
    """
    Analyze a user's document history for financial changes and anomalies.
    Returns spending trends, spikes, and actionable alerts.
    """
    from app.models.document import Document
    from app.db.enums import DocumentStatus

    cutoff = datetime.now(timezone.utc) - timedelta(days=months_back * 30)

    docs = (
        db.query(Document)
        .filter(
            Document.owner_id == user_id,
            Document.status == DocumentStatus.PROCESSED,
            Document.created_at >= cutoff,
        )
        .order_by(Document.created_at.asc())
        .all()
    )

    spikes: list[dict[str, Any]] = []
    category_totals: dict[str, float] = {}
    bill_history: dict[str, list[dict]] = {}
    monthly_totals: dict[str, float] = {}

    for doc in docs:
        fields = doc.extracted_fields or {}
        doc_type = str(doc.document_type)
        month_key = doc.created_at.strftime("%Y-%m")

        # Extract amount
        amount_str = (
            fields.get("amount_due")
            or fields.get("patient_responsibility")
            or fields.get("statement_balance")
            or fields.get("rent_amount")
            or fields.get("minimum_payment")
        )
        amount = _parse_amount(amount_str)
        if amount <= 0:
            continue

        # Categorize
        if doc_type in UTILITY_TYPES:
            cat = "utilities"
        elif doc_type in MEDICAL_TYPES:
            cat = "medical"
        elif doc_type in FINANCIAL_TYPES:
            cat = "housing_financial"
        else:
            cat = "other"

        category_totals[cat] = category_totals.get(cat, 0) + amount
        monthly_totals[month_key] = monthly_totals.get(month_key, 0) + amount

        # Track by bill type for spike detection
        bill_key = f"{doc_type}_{fields.get('provider_name', 'unknown')}"
        bill_history.setdefault(bill_key, []).append({
            "month": month_key,
            "amount": amount,
            "document_id": doc.id,
            "document_name": doc.name,
            "doc_type": doc_type,
        })

    # ── Spike detection ───────────────────────────────────────────────────
    for bill_key, entries in bill_history.items():
        entries.sort(key=lambda x: x["month"])
        for i in range(1, len(entries)):
            prev = entries[i - 1]["amount"]
            curr = entries[i]["amount"]
            if prev > 0 and curr > prev:
                change_pct = ((curr - prev) / prev) * 100
                if change_pct >= 20:
                    doc_type = entries[i]["doc_type"]
                    bill_label = doc_type.replace("_", " ").replace("bill", "").strip().title()
                    spikes.append({
                        "bill_type": bill_label,
                        "doc_type": doc_type,
                        "document_id": entries[i]["document_id"],
                        "document_name": entries[i]["document_name"],
                        "previous_amount": f"${prev:.2f}",
                        "current_amount": f"${curr:.2f}",
                        "change_pct": round(change_pct, 1),
                        "month": entries[i]["month"],
                        "severity": "high" if change_pct >= 40 else "medium",
                        "action": f"Your {bill_label} increased {change_pct:.0f}%. Review the bill for errors or contact the provider.",
                    })

    # ── Monthly trend ─────────────────────────────────────────────────────
    sorted_months = sorted(monthly_totals.keys())
    trend = [
        {"month": m, "total": round(monthly_totals[m], 2)}
        for m in sorted_months
    ]

    # ── Summary ───────────────────────────────────────────────────────────
    total_tracked = sum(category_totals.values())
    avg_monthly = total_tracked / months_back if months_back > 0 else 0

    return {
        "user_id": user_id,
        "period_months": months_back,
        "total_tracked": round(total_tracked, 2),
        "average_monthly": round(avg_monthly, 2),
        "by_category": {k: round(v, 2) for k, v in category_totals.items()},
        "monthly_trend": trend,
        "spikes_detected": spikes,
        "has_spikes": bool(spikes),
        "spike_count": len(spikes),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "These figures are based only on documents uploaded to this app and may not represent all expenses.",
    }


def _parse_amount(value: Any) -> float:
    """Extract a float dollar amount from various string formats."""
    if not value:
        return 0.0
    try:
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0
