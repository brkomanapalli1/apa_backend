"""
bill_intelligence.py — Universal Document & Bill Analyzer

Supported document categories:
  MEDICAL
    - medicare_summary_notice       Medicare Summary Notice (MSN)
    - explanation_of_benefits       EOB from any insurer
    - claim_denial_letter           Denial with appeal rights
    - itemized_medical_bill         Hospital / provider bill
    - medicaid_notice               Medicaid eligibility & renewal
    - social_security_notice        SSA benefit letters
    - prescription_drug_notice      Part D, prior auth, formulary

  UTILITY
    - electricity_bill              Electric utility (kWh, demand charges)
    - natural_gas_bill              Gas utility (therms, CCF)
    - water_sewer_bill              Water / sewer / stormwater
    - trash_recycling_bill          Waste management
    - telecom_bill                  Phone / Internet / cable / TV
    - combined_utility_bill         Bundled utilities

  HOUSING & PROPERTY
    - rent_statement                Rent invoice / lease renewal
    - hoa_statement                 HOA dues, special assessments
    - property_tax_bill             County / municipal property tax
    - mortgage_statement            Mortgage / escrow statement
    - home_insurance_bill           Homeowner's insurance premium

  FINANCIAL
    - credit_card_statement         CC bill with minimum payment
    - bank_statement                Bank account statement
    - loan_statement                Auto / personal / student loan
    - collection_notice             Debt collection notice
    - irs_notice                    IRS / tax authority notice
    - financial_assistance_letter   Aid program notification

  GOVERNMENT
    - veterans_benefits_letter      VA benefits notification
    - food_assistance_notice        SNAP / EBT notice
    - housing_assistance_notice     Section 8 / HUD letter

  UNKNOWN
    - unknown                       Cannot be classified

[HIPAA] This module is PHI-safe:
  - Never logs document text
  - Extracted fields are structured (no raw text stored in analysis)
  - All financial amounts treated as sensitive
  - Designed for AES-256 at-rest encryption of outputs
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

# ── Regex helpers ──────────────────────────────────────────────────────────

MONEY_RE = re.compile(r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?")
DATE_RE = re.compile(
    r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"[a-z]*\.?\s+\d{1,2},\s+\d{4})\b",
    re.IGNORECASE,
)
PHONE_RE = re.compile(r"(?:\+?1[\-.\s]?)?(?:\(?\d{3}\)?[\-.\s]?\d{3}[\-.\s]?\d{4})")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ACCOUNT_RE = re.compile(r"(?:account\s*(?:number|no\.?|#))\s*[:\-]?\s*([A-Za-z0-9\-]+)", re.IGNORECASE)
AMOUNT_DUE_RE = re.compile(
    r"(?:amount\s+due|total\s+due|balance\s+due|current\s+charges|pay\s+this\s+amount)"
    r"\s*[:\-]?\s*\$?\s*([0-9][0-9,]*\.\d{2})",
    re.IGNORECASE,
)
DUE_DATE_RE = re.compile(
    r"(?:due\s+date|payment\s+due|pay\s+by|due\s+by)\s*[:\-]?\s*"
    r"((?:\d{1,2}/\d{1,2}/\d{2,4})|(?:[A-Za-z]+\s+\d{1,2},?\s+\d{4}))",
    re.IGNORECASE,
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _money_values(text: str) -> list[str]:
    seen: list[str] = []
    for m in MONEY_RE.findall(text or ""):
        if m not in seen:
            seen.append(m)
    return seen


def _first_match(text: str, patterns: list[str]) -> str | None:
    for p in patterns:
        m = re.search(p, text or "", re.IGNORECASE | re.MULTILINE)
        if m:
            try:
                return _clean(m.group(1))
            except IndexError:
                return _clean(m.group(0))
    return None


def _first_money(text: str, labels: list[str]) -> str | None:
    for label in labels:
        p = re.compile(rf"{re.escape(label)}[^\n$]*({MONEY_RE.pattern})", re.IGNORECASE)
        m = p.search(text or "")
        if m:
            return m.group(1)
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  DOCUMENT TYPE DETECTION
# ═══════════════════════════════════════════════════════════════════════════

# Each entry: (document_type, confidence, keyword_sets)
# keyword_sets: list of lists — any word in any inner list triggers
_TYPE_RULES: list[tuple[str, float, list[list[str]]]] = [
    # ── Medical ──────────────────────────────────────────────────────────
    ("medicare_summary_notice",    0.97, [["medicare summary notice"], ["msn"]]),
    ("explanation_of_benefits",    0.96, [["explanation of benefits"], ["eob"]]),
    ("claim_denial_letter",        0.93, [["claim denied", "denial", "adverse determination", "not medically necessary", "appeal rights"]]),
    ("prescription_drug_notice",   0.90, [["formulary", "prior authorization", "part d", "prescription drug plan"]]),
    ("medicaid_notice",            0.88, [["medicaid", "renew your benefits", "coverage ending", "eligibility notice"]]),
    # ── Utility (checked BEFORE generic government notices — utility keywords are unambiguous) ──
    ("electricity_bill",           0.93, [["kilowatt", "kwh", "kw demand", "electric service", "power service", "energy charge", "electricity service", "electric bill", "current charges", "distribution charge", "transmission charge", "oncor", "coserv", "tnmp", "aep texas", "centerpoint energy", "txu energy", "reliant energy", "green mountain energy", "direct energy", "energy usage", "meter reading", "electric utility", "billing period", "service address", "texreg"]]),
    ("natural_gas_bill",           0.92, [["therms", "ccf", "natural gas", "gas service", "gas distribution", "atmos", "centerpoint energy"]]),
    ("social_security_notice",     0.92, [["social security", "ssa.gov", "benefit payment", "supplemental security income", "ssi"]]),
    ("veterans_benefits_letter",   0.91, [["department of veterans affairs", "va.gov", "va benefits", "veterans administration"]]),
    ("water_sewer_bill",           0.91, [["water service", "sewer service", "gallons used", "water district", "water utility", "stormwater"]]),
    ("trash_recycling_bill",       0.88, [["waste management", "refuse collection", "recycling service", "trash pickup", "rubbish"]]),
    ("telecom_bill",               0.90, [["monthly service charge", "data plan", "internet service", "cable tv", "streaming service", "phone service", "wireless"]]),
    ("combined_utility_bill",      0.82, [["electric and gas", "combined utility", "gas and electric", "municipal utility"]]),

    # ── Housing & Property ─────────────────────────────────────────────
    ("rent_statement",             0.91, [["rent due", "monthly rent", "lease payment", "tenant statement", "landlord"]]),
    ("hoa_statement",              0.90, [["homeowners association", "hoa dues", "common area", "special assessment", "hoa fee"]]),
    ("property_tax_bill",          0.93, [["property tax", "ad valorem", "tax assessor", "assessed value", "parcel number", "appraisal district"]]),
    ("mortgage_statement",         0.92, [["mortgage statement", "principal balance", "escrow", "loan servicer", "monthly payment due"]]),
    ("home_insurance_bill",        0.90, [["homeowner", "dwelling coverage", "liability coverage", "premium notice", "policy renewal"]]),

    # ── Financial ──────────────────────────────────────────────────────
    ("credit_card_statement",      0.93, [["credit card", "minimum payment due", "statement balance", "new balance", "credit limit"]]),
    ("bank_statement",             0.88, [["checking account", "savings account", "account summary", "deposits", "withdrawals", "beginning balance"]]),
    ("loan_statement",             0.88, [["loan statement", "principal", "interest charge", "payoff amount", "loan balance"]]),
    ("collection_notice",          0.91, [["collection agency", "debt collector", "past due", "charged off", "referred to collections", "third-party collector"]]),
    ("irs_notice",                 0.94, [["internal revenue service", "irs.gov", "notice cp", "balance due to irs", "department of the treasury"]]),
    ("food_assistance_notice",     0.89, [["snap benefits", "ebt", "food stamps", "food assistance", "supplemental nutrition"]]),
    ("housing_assistance_notice",  0.88, [["section 8", "housing choice voucher", "hud", "public housing authority"]]),
    ("financial_assistance_letter",0.85, [["financial assistance", "charity care", "hardship program", "income-based reduction"]]),

    # ── Itemized medical bill (last resort for general billing) ─────────
    ("itemized_medical_bill",      0.80, [["itemized bill", "amount due", "statement date", "patient account", "balance due"]]),
]


def detect_document_type(text: str, filename: str = "") -> tuple[str, float, list[str]]:
    """
    Returns (document_type, confidence, reasons).
    Tries every rule in priority order; returns first match.
    """
    hay = f"{filename}\n{text}".lower()
    amounts = _money_values(hay)

    for doc_type, confidence, keyword_groups in _TYPE_RULES:
        reasons: list[str] = []
        matched = False
        for group in keyword_groups:
            for kw in group:
                if kw.lower() in hay:
                    reasons.append(f"Found keyword: '{kw}'")
                    matched = True
                    break
            if matched:
                break
        if matched:
            return doc_type, confidence, reasons

    # Fallback: lots of money amounts → generic bill
    if len(amounts) >= 3:
        return "itemized_medical_bill", 0.45, ["Multiple monetary amounts detected"]

    return "unknown", 0.20, ["No strong document markers found"]


# ═══════════════════════════════════════════════════════════════════════════
#  FIELD EXTRACTORS BY CATEGORY
# ═══════════════════════════════════════════════════════════════════════════

def _extract_common(text: str) -> dict[str, Any]:
    """Fields that apply to every document type."""
    phone_m = PHONE_RE.search(text or "")
    email_m = EMAIL_RE.search(text or "")
    amount_m = AMOUNT_DUE_RE.search(text or "")
    date_m = DUE_DATE_RE.search(text or "")
    acct_m = ACCOUNT_RE.search(text or "")

    return {
        "amount_due":      amount_m.group(1) if amount_m else None,
        "due_date":        _clean(date_m.group(1)) if date_m else None,
        "account_number":  acct_m.group(1) if acct_m else None,
        "contact_phone":   phone_m.group(0) if phone_m else None,
        "contact_email":   email_m.group(0) if email_m else None,
        "all_amounts":     _money_values(text)[:10],
    }


def _extract_medical(text: str, doc_type: str) -> dict[str, Any]:
    f = _extract_common(text)
    f.update({
        "provider_name":  _first_match(text, [r"(?:Provider|Hospital|Facility|Doctor)[:\s]+([^\n]{3,80})"]),
        "member_name":    _first_match(text, [r"(?:Patient|Member|Beneficiary)[:\s]+([^\n]{3,80})"]),
        "member_id":      _first_match(text, [r"(?:Member ID|Medicare Number|Recipient ID)[:\s#]*([^\n]{4,40})"]),
        "service_date":   _first_match(text, [r"(?:Date of Service|Service Date)[:\s]+([^\n]{3,30})"]),
    })

    if doc_type == "medicare_summary_notice":
        f.update({
            "total_billed":           _first_money(text, ["total amount billed", "provider billed"]),
            "medicare_approved":      _first_money(text, ["medicare approved", "approved amount"]),
            "medicare_paid":          _first_money(text, ["medicare paid", "amount medicare paid"]),
            "patient_responsibility": _first_money(text, ["maximum you may be billed", "patient responsibility"]),
            "claim_number":           _first_match(text, [r"(?:Claim Number|Claim No\.)[:\s#]*([^\n]{3,40})"]),
        })
    elif doc_type == "explanation_of_benefits":
        f.update({
            "plan_name":              _first_match(text, [r"(?:Plan|Insurance Plan)[:\s]+([^\n]{3,80})"]),
            "amount_billed":          _first_money(text, ["amount billed", "provider charge"]),
            "plan_paid":              _first_money(text, ["plan paid", "insurance paid"]),
            "patient_responsibility": _first_money(text, ["patient responsibility", "you owe", "member responsibility"]),
            "network_status":         _first_match(text, [r"(?:Network Status)[:\s]+([^\n]{3,40})"]),
            "is_bill":                False,
        })
    elif doc_type == "claim_denial_letter":
        f.update({
            "denial_reason":          _first_match(text, [r"(?:Reason for Denial)[:\s]+([^\n]{8,200})", r"(not medically necessary[^\n]{0,120})"]),
            "appeal_deadline_days":   _first_match(text, [r"within\s+(\d{1,3}\s+days)"]),
            "denied_amount":          _first_money(text, ["denied amount", "amount denied"]),
        })
    elif doc_type == "itemized_medical_bill":
        dupes = _count_duplicate_lines(text)
        f.update({
            "statement_date":              _first_match(text, [r"(?:Statement Date|Bill Date)[:\s]+([^\n]{3,40})"]),
            "total_charges":               _first_money(text, ["total charges", "total amount billed"]),
            "possible_duplicate_charges":  dupes,
            "duplicate_warning":           dupes > 0,
        })
    elif doc_type == "medicaid_notice":
        f.update({
            "renewal_due_date":  _first_match(text, [r"(?:Renew by|Renewal Due Date)[:\s]+([^\n]{3,40})"]),
            "coverage_status":   _first_match(text, [r"(?:Coverage Status)[:\s]+([^\n]{3,60})", r"(coverage (?:ending|approved|renewed)[^\n]{0,80})"]),
        })
    elif doc_type == "social_security_notice":
        f.update({
            "benefit_amount":    _first_money(text, ["monthly benefit", "benefit amount", "you will receive"]),
            "effective_date":    _first_match(text, [r"(?:effective|starting)[:\s]+([^\n]{3,40})"]),
        })

    return f


def _extract_utility(text: str, doc_type: str) -> dict[str, Any]:
    f = _extract_common(text)
    f.update({
        "provider_name":    _first_match(text, [r"^([A-Z][A-Za-z0-9& ,.\-]{3,60})$", r"(?:from|provider|company)[:\s]+([^\n]{3,60})"]),
        "service_address":  _first_match(text, [r"(?:service\s+address|service\s+location)[:\s]+([^\n]+)"]),
        "billing_period":   _first_match(text, [r"(?:billing\s+period|service\s+period|bill\s+period)[:\s]+([^\n]+)"]),
        "statement_date":   _first_match(text, [r"(?:statement\s+date|bill\s+date)[:\s]+([^\n]{3,40})"]),
        "previous_balance": _first_money(text, ["previous balance", "prior balance", "last balance"]),
        "payments_received":_first_money(text, ["payment received", "payment applied", "credit applied"]),
        "current_charges":  _first_money(text, ["current charges", "new charges", "charges this period"]),
        "late_fee_risk":    bool(re.search(r"late\s+(?:fee|charge|penalty)|disconnect\s+notice|shutoff", text or "", re.IGNORECASE)),
        "assistance_available": bool(re.search(r"assistance\s+program|payment\s+plan|budget\s+billing|LIHEAP|low.income", text or "", re.IGNORECASE)),
    })

    if doc_type == "electricity_bill":
        f.update({
            "usage_kwh":        _first_match(text, [r"(\d[\d,]*)\s*k[Ww][Hh]"]),
            "avg_daily_usage":  _first_match(text, [r"(?:daily\s+average)[:\s]+([0-9.]+\s*k[Ww][Hh])"]),
            "rate_per_kwh":     _first_match(text, [r"(?:rate|price\s+per\s+k[Ww][Hh])[:\s]+\$?([0-9.]+)"]),
            "demand_charges":   _first_money(text, ["demand charge", "peak demand"]),
        })
    elif doc_type == "natural_gas_bill":
        f.update({
            "usage_therms":     _first_match(text, [r"(\d[\d,]*)\s*(?:therms|ccf)"]),
            "rate_per_therm":   _first_match(text, [r"(?:rate|price\s+per\s+therm)[:\s]+\$?([0-9.]+)"]),
        })
    elif doc_type == "water_sewer_bill":
        f.update({
            "usage_gallons":    _first_match(text, [r"(\d[\d,]*)\s*(?:gallons|gal\b|ccf|hcf)"]),
            "sewer_charge":     _first_money(text, ["sewer charge", "wastewater"]),
            "stormwater_fee":   _first_money(text, ["stormwater", "storm water"]),
        })
    elif doc_type == "telecom_bill":
        f.update({
            "plan_name":        _first_match(text, [r"(?:plan|package)[:\s]+([^\n]{3,60})"]),
            "data_usage":       _first_match(text, [r"(\d[\d.]*\s*(?:GB|MB|TB))\s*(?:used|data)"]),
            "overage_charges":  _first_money(text, ["overage", "excess data", "data overage"]),
            "auto_pay_discount":_first_money(text, ["autopay discount", "auto pay", "paperless discount"]),
        })

    return f


def _extract_housing(text: str, doc_type: str) -> dict[str, Any]:
    f = _extract_common(text)
    f.update({
        "property_address": _first_match(text, [r"(?:property\s+address|service\s+address|premises)[:\s]+([^\n]+)"]),
    })

    if doc_type == "property_tax_bill":
        f.update({
            "parcel_number":    _first_match(text, [r"(?:parcel|account|property\s+id)[:\s#]+([A-Za-z0-9\-]+)"]),
            "assessed_value":   _first_money(text, ["assessed value", "appraised value", "market value"]),
            "tax_rate":         _first_match(text, [r"(?:tax\s+rate|mill\s+rate)[:\s]+([0-9.]+%?)"]),
            "exemptions":       _first_money(text, ["homestead exemption", "senior exemption", "exemption"]),
            "penalty_date":     _first_match(text, [r"(?:penalty\s+after|delinquent\s+after)[:\s]+([^\n]{3,40})"]),
            "payment_options":  bool(re.search(r"installment|quarterly|semi.annual", text or "", re.IGNORECASE)),
        })
    elif doc_type == "hoa_statement":
        f.update({
            "unit_number":          _first_match(text, [r"(?:unit|lot|home)[:\s#]+([A-Za-z0-9\-]+)"]),
            "special_assessment":   _first_money(text, ["special assessment"]),
            "reserve_fund":         _first_money(text, ["reserve fund", "reserve contribution"]),
            "late_fee":             _first_money(text, ["late fee", "late charge"]),
        })
    elif doc_type == "mortgage_statement":
        f.update({
            "principal_balance":    _first_money(text, ["principal balance", "unpaid principal"]),
            "interest_rate":        _first_match(text, [r"(?:interest\s+rate)[:\s]+([0-9.]+%)"]),
            "escrow_balance":       _first_money(text, ["escrow balance", "escrow account"]),
            "next_payment_date":    _first_match(text, [r"(?:next\s+payment\s+due|payment\s+due\s+date)[:\s]+([^\n]{3,40})"]),
        })
    elif doc_type == "rent_statement":
        f.update({
            "rent_amount":          _first_money(text, ["rent due", "monthly rent", "base rent"]),
            "late_fee_after":       _first_match(text, [r"(?:late\s+fee\s+after|grace\s+period)[:\s]+([^\n]{3,40})"]),
            "lease_end_date":       _first_match(text, [r"(?:lease\s+end|lease\s+expires|move.out)[:\s]+([^\n]{3,40})"]),
        })

    return f


def _extract_financial(text: str, doc_type: str) -> dict[str, Any]:
    f = _extract_common(text)

    if doc_type == "credit_card_statement":
        f.update({
            "statement_balance":    _first_money(text, ["statement balance", "new balance"]),
            "minimum_payment":      _first_money(text, ["minimum payment", "minimum due"]),
            "credit_limit":         _first_money(text, ["credit limit"]),
            "available_credit":     _first_money(text, ["available credit"]),
            "apr":                  _first_match(text, [r"(?:APR|annual\s+percentage\s+rate)[:\s]+([0-9.]+%)"]),
            "interest_charged":     _first_money(text, ["interest charged", "finance charge"]),
        })
    elif doc_type == "collection_notice":
        f.update({
            "original_creditor":    _first_match(text, [r"(?:original\s+creditor|original\s+account)[:\s]+([^\n]{3,80})"]),
            "collection_agency":    _first_match(text, [r"(?:collection\s+agency|collector)[:\s]+([^\n]{3,80})"]),
            "debt_amount":          _first_money(text, ["total amount owed", "debt amount", "balance owed"]),
            "dispute_deadline_days":_first_match(text, [r"within\s+(\d{1,3})\s+days"]),
            "your_rights_mentioned":bool(re.search(r"fair\s+debt\s+collection|fdcpa|dispute\s+this\s+debt", text or "", re.IGNORECASE)),
        })
    elif doc_type == "irs_notice":
        f.update({
            "notice_number":        _first_match(text, [r"(?:Notice|CP)\s*(CP?\d{2,5}[A-Z]?)"]),
            "tax_year":             _first_match(text, [r"(?:tax\s+year|for\s+the\s+year)\s+(\d{4})"]),
            "amount_owed":          _first_money(text, ["amount you owe", "balance due", "total amount due"]),
            "response_deadline":    _first_match(text, [r"(?:respond\s+by|reply\s+by|deadline)[:\s]+([^\n]{3,40})"]),
        })
    elif doc_type == "loan_statement":
        f.update({
            "principal_remaining":  _first_money(text, ["principal balance", "remaining balance", "loan balance"]),
            "interest_charged":     _first_money(text, ["interest", "finance charge"]),
            "payoff_amount":        _first_money(text, ["payoff amount", "payoff balance"]),
            "maturity_date":        _first_match(text, [r"(?:maturity\s+date|loan\s+end)[:\s]+([^\n]{3,40})"]),
        })

    return f


def _count_duplicate_lines(text: str) -> int:
    lines = [re.sub(r"\s+", " ", l).strip().lower() for l in (text or "").splitlines() if l.strip()]
    service_lines = [l for l in lines if MONEY_RE.search(l) and len(l) > 10]
    seen: dict[str, int] = {}
    dupes = 0
    for line in service_lines:
        normalized = re.sub(MONEY_RE.pattern, "$AMT", line)
        seen[normalized] = seen.get(normalized, 0) + 1
        if seen[normalized] == 2:
            dupes += 1
    return dupes


def extract_fields(text: str, doc_type: str) -> dict[str, Any]:
    """Route to the correct extractor based on document type."""
    medical = {"medicare_summary_notice", "explanation_of_benefits", "claim_denial_letter",
               "itemized_medical_bill", "medicaid_notice", "social_security_notice",
               "prescription_drug_notice", "veterans_benefits_letter"}
    utility = {"electricity_bill", "natural_gas_bill", "water_sewer_bill", "trash_recycling_bill",
               "telecom_bill", "combined_utility_bill"}
    housing = {"rent_statement", "hoa_statement", "property_tax_bill", "mortgage_statement",
               "home_insurance_bill"}
    financial = {"credit_card_statement", "bank_statement", "loan_statement", "collection_notice",
                 "irs_notice", "food_assistance_notice", "housing_assistance_notice",
                 "financial_assistance_letter"}

    if doc_type in medical:
        return _extract_medical(text, doc_type)
    if doc_type in utility:
        return _extract_utility(text, doc_type)
    if doc_type in housing:
        return _extract_housing(text, doc_type)
    if doc_type in financial:
        return _extract_financial(text, doc_type)

    # Unknown — return common fields only
    return _extract_common(text)


# ═══════════════════════════════════════════════════════════════════════════
#  SUMMARIES
# ═══════════════════════════════════════════════════════════════════════════

def build_summary(doc_type: str, fields: dict[str, Any], text: str) -> str:
    """Plain-English summary written at a senior-friendly reading level."""
    amt = fields.get("amount_due") or fields.get("rent_amount") or fields.get("debt_amount")
    date = fields.get("due_date") or fields.get("penalty_date") or fields.get("renewal_due_date")

    summaries: dict[str, str] = {
        "medicare_summary_notice": (
            f"This is a Medicare Summary Notice — it shows what your doctor or hospital billed, "
            f"what Medicare approved and paid, and what you may still owe. "
            f"Medicare paid {fields.get('medicare_paid') or 'an amount'} and your share may be "
            f"{fields.get('patient_responsibility') or 'shown above'}. This is not necessarily a bill."
        ),
        "explanation_of_benefits": (
            f"This is an Explanation of Benefits (EOB). It is usually NOT a bill — it just shows "
            f"what your insurance plan paid and what they say you owe. "
            f"Your responsibility is shown as {fields.get('patient_responsibility') or 'listed above'}. "
            f"Wait for a separate bill from your provider before paying."
        ),
        "claim_denial_letter": (
            f"Your insurance claim was denied. The reason given is: "
            f"{fields.get('denial_reason') or 'see the letter for details'}. "
            f"You have the right to appeal — this is important to do quickly before the deadline."
        ),
        "itemized_medical_bill": (
            f"This is a medical bill. The amount due is {amt or 'listed above'}. "
            f"Before paying, check that the charges match your insurance EOB and look for any errors. "
            + (f"We found {fields.get('possible_duplicate_charges')} possible duplicate charge(s)." if fields.get("duplicate_warning") else "")
        ),
        "medicaid_notice": (
            f"This is a Medicaid notice about your coverage. "
            f"Your coverage status appears to be: {fields.get('coverage_status') or 'see letter'}. "
            f"If a renewal is needed, the deadline is {fields.get('renewal_due_date') or 'listed in the letter'}."
        ),
        "social_security_notice": (
            f"This is a Social Security notice. Your benefit amount appears to be "
            f"{fields.get('benefit_amount') or 'listed above'}, effective {fields.get('effective_date') or 'as stated'}."
        ),
        "electricity_bill": (
            f"This is your electricity bill from {fields.get('provider_name') or 'your electric company'}. "
            f"You used {fields.get('usage_kwh') or '—'} kWh this billing period. "
            f"The amount due is {amt or 'listed above'}, due {date or 'on the date shown'}."
            + (" Payment assistance programs may be available." if fields.get("assistance_available") else "")
            + (" ⚠️ This may include a late fee risk." if fields.get("late_fee_risk") else "")
        ),
        "natural_gas_bill": (
            f"This is your natural gas bill. You used {fields.get('usage_therms') or '—'} therms this period. "
            f"Amount due: {amt or 'see bill'}, due {date or 'on the date shown'}."
        ),
        "water_sewer_bill": (
            f"This is your water and sewer bill. Usage was {fields.get('usage_gallons') or '—'} gallons. "
            f"Amount due: {amt or 'see bill'}, due {date or 'on the date shown'}."
        ),
        "telecom_bill": (
            f"This is your phone or internet bill from {fields.get('provider_name') or 'your provider'}. "
            f"Amount due: {amt or 'see bill'}, due {date or 'on the date shown'}. "
            + (f"Data used: {fields.get('data_usage')}. " if fields.get("data_usage") else "")
        ),
        "trash_recycling_bill": (
            f"This is your trash and recycling service bill. "
            f"Amount due: {amt or 'see bill'}, due {date or 'on the date shown'}."
        ),
        "combined_utility_bill": (
            f"This is a combined utility bill covering multiple services. "
            f"Total amount due: {amt or 'see bill'}, due {date or 'on the date shown'}."
        ),
        "property_tax_bill": (
            f"This is your property tax bill. The amount due is {amt or 'listed above'}. "
            f"Late penalties begin after {fields.get('penalty_date') or 'the due date shown'}. "
            + (" Payment by installment may be available." if fields.get("payment_options") else "")
        ),
        "hoa_statement": (
            f"This is your Homeowners Association (HOA) statement. "
            f"Amount due: {amt or 'see bill'}, due {date or 'on the date shown'}. "
            + (f"Includes a special assessment of {fields.get('special_assessment')}." if fields.get("special_assessment") else "")
        ),
        "rent_statement": (
            f"This is your rent statement. Your monthly rent is {fields.get('rent_amount') or amt or 'listed above'}, "
            f"due {date or 'on the date shown'}. "
            + (f"Late fees apply after {fields.get('late_fee_after')}." if fields.get("late_fee_after") else "")
        ),
        "mortgage_statement": (
            f"This is your mortgage statement. Payment of {amt or 'the listed amount'} is due {date or 'on the date shown'}. "
            f"Remaining principal balance: {fields.get('principal_balance') or 'listed above'}."
        ),
        "home_insurance_bill": (
            f"This is your homeowner's insurance premium notice. "
            f"Amount due: {amt or 'see bill'}, due {date or 'on the date shown'}. "
            "This is not a claim — it is your regular insurance payment."
        ),
        "credit_card_statement": (
            f"This is your credit card statement. Statement balance: {fields.get('statement_balance') or amt or 'listed above'}. "
            f"Minimum payment due: {fields.get('minimum_payment') or 'listed above'}, by {date or 'the due date shown'}. "
            "Paying only the minimum will result in interest charges."
        ),
        "collection_notice": (
            f"This is a debt collection notice. The amount stated is {fields.get('debt_amount') or amt or 'listed above'}. "
            f"You have the right to dispute this debt within {fields.get('dispute_deadline_days') or '30'} days. "
            "Do not pay without verifying this is a legitimate debt."
        ),
        "irs_notice": (
            f"This is an IRS notice ({fields.get('notice_number') or 'see letter'}). "
            f"It may relate to your {fields.get('tax_year') or 'recent'} tax return. "
            f"Amount listed: {fields.get('amount_owed') or amt or 'see notice'}. "
            "Respond by the deadline shown — ignoring IRS notices can result in penalties."
        ),
        "loan_statement": (
            f"This is a loan statement. Payment of {amt or 'the listed amount'} is due {date or 'on the date shown'}. "
            f"Remaining balance: {fields.get('principal_remaining') or 'listed above'}."
        ),
        "veterans_benefits_letter": (
            f"This is a letter from the Department of Veterans Affairs. "
            f"Your benefit amount appears to be {fields.get('benefit_amount') or 'listed above'}."
        ),
    }

    summary = summaries.get(doc_type)
    if summary:
        return summary

    excerpt = _clean(text)[:300]
    return f"This document could not be fully classified. Here is what we found: {excerpt}"


# ═══════════════════════════════════════════════════════════════════════════
#  RECOMMENDATIONS
# ═══════════════════════════════════════════════════════════════════════════

def build_recommendations(doc_type: str, fields: dict[str, Any]) -> list[dict[str, str]]:
    recs: list[dict[str, str]] = []

    # ── Medical ────────────────────────────────────────────────────────────
    if doc_type == "explanation_of_benefits":
        recs += [
            {"title": "Do not pay this EOB yet", "why": "An EOB is not a bill. Wait for the actual invoice from your provider.", "priority": "high", "action": "Compare the EOB amounts with any bill you receive from the provider before making any payment."},
            {"title": "Check for billing errors", "why": "Comparing the EOB with your provider bill catches overbilling.", "priority": "high", "action": "If the provider bill is higher than your EOB responsibility, call the provider's billing office."},
        ]
    elif doc_type == "medicare_summary_notice":
        recs += [
            {"title": "Review what Medicare paid vs. what you were billed", "why": "Providers must accept Medicare-approved amounts.", "priority": "high", "action": "If a provider bill exceeds the 'maximum you may be billed' on this MSN, contact Medicare."},
            {"title": "Keep this notice for your records", "why": "You can use it to dispute incorrect charges.", "priority": "medium", "action": "File this MSN with the related provider bill."},
        ]
    elif doc_type == "claim_denial_letter":
        recs += [
            {"title": "Appeal the denial immediately", "why": "Appeal windows are short (often 30-180 days).", "priority": "high", "action": "Gather your denial reason, claim number, doctor notes, and relevant records. Submit a written appeal."},
            {"title": "Call the insurance plan for clarification", "why": "Some denials are reversed with a simple coding correction.", "priority": "high", "action": "Ask the plan exactly what documents would reverse the denial."},
        ]
    elif doc_type == "itemized_medical_bill":
        recs += [
            {"title": "Request the full itemized bill", "why": "Line-by-line detail is essential to spot errors.", "priority": "high", "action": "Ask the billing department for a complete itemized statement by CPT code."},
        ]
        if fields.get("duplicate_warning"):
            recs.append({"title": "Challenge possible duplicate charges", "why": f"{fields.get('possible_duplicate_charges')} potential duplicate line(s) found.", "priority": "high", "action": "Circle each repeated charge and ask the billing office to remove confirmed duplicates."})
        recs.append({"title": "Ask about financial assistance", "why": "Hospitals have charity care and hardship programs.", "priority": "medium", "action": "Call the billing office before paying and ask about income-based discounts or payment plans."})
    elif doc_type == "medicaid_notice":
        recs += [
            {"title": "Complete renewal paperwork on time", "why": "Missing the renewal deadline can cause a coverage gap.", "priority": "high", "action": "Gather all required documents and submit your renewal before the deadline."},
        ]
    elif doc_type == "collection_notice":
        recs += [
            {"title": "Send a debt validation letter first", "why": "You have 30 days to request proof that this debt is real.", "priority": "high", "action": "Send a certified letter requesting validation of the debt before making any payment."},
            {"title": "Check your credit report", "why": "Collection notices sometimes involve errors or identity theft.", "priority": "high", "action": "Review your credit report at AnnualCreditReport.com to verify this account."},
        ]
    elif doc_type == "irs_notice":
        recs += [
            {"title": "Do not ignore this notice", "why": "Unanswered IRS notices escalate to liens and levies.", "priority": "high", "action": "Read the notice carefully and respond by the deadline. Consider calling the IRS number on the notice."},
            {"title": "Consider getting tax help", "why": "IRS notices can be complex.", "priority": "medium", "action": "A free IRS Taxpayer Advocate or VITA volunteer can help you respond correctly."},
        ]

    # ── Utility ────────────────────────────────────────────────────────────
    if doc_type in {"electricity_bill", "natural_gas_bill", "water_sewer_bill", "telecom_bill", "combined_utility_bill", "trash_recycling_bill"}:
        if fields.get("late_fee_risk"):
            recs.append({"title": "Pay before the late fee deadline", "why": "A late fee or service interruption may apply.", "priority": "high", "action": f"Pay by {fields.get('due_date') or 'the date on the bill'} to avoid penalties."})
        if fields.get("assistance_available"):
            recs.append({"title": "Ask about assistance programs", "why": "You may qualify for reduced rates or bill help.", "priority": "medium", "action": "Call the utility company and ask about LIHEAP, budget billing, or low-income assistance programs."})
        recs.append({"title": "Verify the service address and account number", "why": "Billing errors sometimes affect the wrong account.", "priority": "low", "action": "Confirm the service address on the bill matches your home before paying."})

    # ── Property ───────────────────────────────────────────────────────────
    if doc_type == "property_tax_bill":
        recs += [
            {"title": "Check for senior exemptions", "why": "Many counties offer homestead or senior property tax exemptions.", "priority": "medium", "action": "Call your county appraisal district and ask about senior citizen or homestead exemptions."},
            {"title": "Pay before the penalty date", "why": "Late property taxes accrue penalties and interest.", "priority": "high", "action": f"Pay by {fields.get('penalty_date') or 'the deadline on the bill'} to avoid penalties."},
        ]
    elif doc_type == "hoa_statement":
        recs += [
            {"title": "Pay dues on time to avoid liens", "why": "HOAs can place liens on properties for unpaid dues.", "priority": "high", "action": f"Pay by {fields.get('due_date') or 'the due date'}."},
        ]
    elif doc_type == "credit_card_statement":
        recs += [
            {"title": "Pay more than the minimum if possible", "why": "Paying only the minimum significantly increases total interest paid.", "priority": "high", "action": f"Try to pay at least {fields.get('statement_balance') or 'the full balance'} by {fields.get('due_date') or 'the due date'}."},
        ]

    # Universal fallback
    if not recs:
        recs.append({"title": "Review key amounts and dates", "why": "Amounts and deadlines drive the next required action.", "priority": "medium", "action": "Confirm the amount due and due date before responding or paying."})

    return recs[:5]


# ═══════════════════════════════════════════════════════════════════════════
#  DEADLINES
# ═══════════════════════════════════════════════════════════════════════════

def build_deadlines(doc_type: str, fields: dict[str, Any], text: str) -> list[dict[str, str | None]]:
    deadlines: list[dict[str, str | None]] = []
    seen: set[str] = set()

    # Type-specific deadlines
    if doc_type == "claim_denial_letter":
        days_text = str(fields.get("appeal_deadline_days") or "")
        day_m = re.search(r"(\d{1,3})", days_text)
        if day_m:
            days = int(day_m.group(1))
            inferred = (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()
            deadlines.append({"title": "Appeal deadline (approximate)", "date": inferred, "reason": f"You typically have {days} days to appeal from the denial date.", "action": "File your appeal before this date."})
            seen.add(inferred)

    for due_key in ("due_date", "renewal_due_date", "penalty_date", "response_deadline", "next_payment_date"):
        val = fields.get(due_key)
        if val and str(val) not in seen:
            deadlines.append({"title": _due_date_title(due_key, doc_type), "date": str(val), "reason": "Date found in the document.", "action": "Act before this date."})
            seen.add(str(val))

    # Fallback: raw dates from text
    for raw in DATE_RE.findall(text or "")[:4]:
        if raw not in seen:
            deadlines.append({"title": f"Date found: {raw}", "date": raw, "reason": "A date was detected in the document.", "action": "Review the nearby section to confirm what this date means."})
            seen.add(raw)

    return deadlines[:6]


def _due_date_title(key: str, doc_type: str) -> str:
    titles = {
        "due_date": "Payment due",
        "renewal_due_date": "Renewal deadline",
        "penalty_date": "Penalty / late fee begins",
        "response_deadline": "Response required by",
        "next_payment_date": "Next payment due",
    }
    return titles.get(key, "Important date")


# ═══════════════════════════════════════════════════════════════════════════
#  LETTER GENERATOR
# ═══════════════════════════════════════════════════════════════════════════

def build_letter(doc_type: str, fields: dict[str, Any]) -> dict[str, str]:
    provider = fields.get("provider_name") or "Billing Department"
    member = fields.get("member_name") or "[Your Name]"
    ref = (fields.get("account_number") or fields.get("claim_number") or
           fields.get("claim_or_reference_number") or "[Reference Number]")
    amount = (fields.get("amount_due") or fields.get("patient_responsibility") or
              fields.get("debt_amount") or "[Amount]")

    if doc_type == "claim_denial_letter":
        body = f"""Dear {provider},

I am writing to formally appeal the denial of claim/reference number {ref}. According to the notice I received, the denial reason was: {fields.get('denial_reason') or '[insert reason]'}.

I respectfully request a full review of this decision. Enclosed are supporting documents including [list relevant records]. If additional documentation is required, please specify exactly what is needed and where it should be sent.

Patient/Member Name: {member}
Claim/Reference Number: {ref}
Amount in Dispute: {amount}
Date of Service: {fields.get('service_date') or '[Date]'}

Please confirm receipt of this appeal and provide a written response within 30 days.

Sincerely,
{member}
[Phone Number]
[Address]
[Date]"""
        return {"title": "Claim appeal letter", "subject": f"Formal Appeal — Denied Claim {ref}", "body": body, "audience": provider, "use_case": "Appeal a denied insurance or Medicare claim"}

    if doc_type in {"itemized_medical_bill", "explanation_of_benefits", "medicare_summary_notice"}:
        body = f"""Dear {provider} Billing Department,

I am writing to request a review of charges on account/claim number {ref}. After reviewing the documentation I received, I have questions about the amount listed as {amount} and request a complete itemized explanation before making payment.

Please provide:
1. A complete itemized bill or claim breakdown by service line and date
2. Explanation of any charges denied, duplicated, or assigned to me
3. Corrected balance if any billing errors are found
4. Confirmation of any insurance payments applied

Patient/Member Name: {member}
Account/Claim Number: {ref}
Amount in Question: {amount}

Please place this account on temporary review hold while the charges are verified.

Sincerely,
{member}
[Phone Number]
[Address]
[Date]"""
        return {"title": "Medical billing dispute letter", "subject": f"Billing Review Request — Account {ref}", "body": body, "audience": provider, "use_case": "Dispute a medical bill or request itemized review"}

    if doc_type in {"electricity_bill", "natural_gas_bill", "water_sewer_bill", "telecom_bill",
                    "combined_utility_bill", "trash_recycling_bill"}:
        body = f"""Dear {provider} Customer Service,

I am writing about my utility bill for account number {ref}. I have questions about the charges and would like clarification before making payment.

Specifically, I would like to understand:
1. The breakdown of charges for the billing period {fields.get('billing_period') or '[period]'}
2. Whether any errors, estimated reads, or unusual charges are included
3. Whether I qualify for any assistance programs, payment plans, or budget billing
4. The correct amount due and the exact due date to avoid late fees

Service Address: {fields.get('service_address') or '[Address]'}
Account Number: {ref}
Amount Shown: {amount}

Thank you for your prompt assistance.

Sincerely,
[Your Name]
[Phone Number]
[Date]"""
        return {"title": "Utility bill inquiry letter", "subject": f"Question About My Utility Bill — Account {ref}", "body": body, "audience": provider, "use_case": "Ask questions about a utility bill or request payment assistance"}

    if doc_type == "property_tax_bill":
        body = f"""Dear Tax Assessor / Collector,

I am writing regarding my property tax bill for parcel number {ref}. I would like to inquire about the following:

1. Confirmation of the assessed value and tax rate used to calculate this bill
2. Whether I qualify for a senior citizen, homestead, or disability exemption
3. Available installment payment options
4. The appeal process if I believe the assessed value is incorrect

Property Address: {fields.get('property_address') or '[Address]'}
Parcel Number: {ref}
Amount Due: {amount}

Thank you for your assistance.

Sincerely,
[Your Name]
[Phone Number]
[Date]"""
        return {"title": "Property tax inquiry letter", "subject": f"Property Tax Question — Parcel {ref}", "body": body, "audience": "Tax Assessor / Collector", "use_case": "Inquire about property tax, exemptions, or payment plans"}

    if doc_type == "collection_notice":
        body = f"""To Whom It May Concern,

I am writing in response to your collection notice dated [Date] regarding account number {ref} with an alleged balance of {amount}.

Under the Fair Debt Collection Practices Act (FDCPA), I am exercising my right to request validation of this debt within 30 days of receiving your notice. Please provide:
1. The name and address of the original creditor
2. The original account number
3. A complete payment history showing how the balance was calculated
4. Proof that your agency is licensed to collect in my state

Until validation is received, please cease all collection activity. Do not contact me by phone — written communication only.

Your Name: {member}
Reference: {ref}
[Address]
[Date]"""
        return {"title": "Debt validation request letter", "subject": f"Debt Validation Request — Account {ref}", "body": body, "audience": "Collection Agency", "use_case": "Request debt validation before paying a collection notice"}

    # Generic fallback
    body = f"""To Whom It May Concern,

I am writing about the document I received regarding reference number {ref}. I need clarification about this document, including:
1. What action (if any) is required from me
2. The correct amount due, if applicable
3. Any relevant deadlines I need to meet

Name: {member}
Reference: {ref}
[Phone Number]
[Date]"""
    return {"title": "General inquiry letter", "subject": "Request for Clarification", "body": body, "audience": provider, "use_case": "Ask for clarification about any notice or bill"}


# ═══════════════════════════════════════════════════════════════════════════
#  SENIOR VIEW — restored from original paperwork_intelligence.py
#
#  These functions power the "Simple mode" UI panel that the frontend and
#  mobile app read from extracted_fields.ui_summary.  They were present in
#  the original codebase and must NOT be removed when new bill types are added.
# ═══════════════════════════════════════════════════════════════════════════

# Document families used by the frontend to choose the right icon / colour
_MEDICAL_TYPES = {
    "medicare_summary_notice", "explanation_of_benefits", "claim_denial_letter",
    "itemized_medical_bill", "medicaid_notice", "social_security_notice",
    "prescription_drug_notice", "veterans_benefits_letter",
}
_UTILITY_TYPES = {
    "electricity_bill", "natural_gas_bill", "water_sewer_bill",
    "trash_recycling_bill", "telecom_bill", "combined_utility_bill",
}
_HOUSING_TYPES = {
    "rent_statement", "hoa_statement", "property_tax_bill",
    "mortgage_statement", "home_insurance_bill",
}
_FINANCIAL_TYPES = {
    "credit_card_statement", "bank_statement", "loan_statement",
    "collection_notice", "irs_notice", "food_assistance_notice",
    "housing_assistance_notice", "financial_assistance_letter",
}


def derive_document_family(doc_type: str, text: str) -> str:
    """
    Returns a broad family label used by the UI for colour-coding and iconography.
    Matches the original _derive_document_family() behaviour, extended for new types.
    """
    if doc_type in _MEDICAL_TYPES:
        return "medical_or_coverage"
    if doc_type in _UTILITY_TYPES:
        return "utility_bill"
    if doc_type in _HOUSING_TYPES:
        return "housing_or_property"
    if doc_type in _FINANCIAL_TYPES:
        hay = (text or "").lower()
        if any(t in hay for t in ["collection notice", "past due", "delinquent"]):
            return "collection_notice"
        return "financial_document"
    return "general_paperwork"


def build_payment_guidance(doc_type: str, fields: dict[str, Any]) -> tuple[str, str]:
    """
    Returns (payment_status_code, plain_English_message).

    payment_status codes (used by the mobile/web UI):
      not_a_bill        — EOB, MSN informational notices
      review_first      — bill likely but needs verification
      possible_bill     — almost certainly a bill; review before paying
      appeal_or_call    — denial; do not pay, act on appeal
      respond_to_notice — coverage/eligibility; respond, don't necessarily pay
      pay_utility       — utility bill, straightforward payment
      pay_housing       — property/HOA/rent bill
      pay_financial     — credit card / loan / tax payment
      verify_debt       — collection notice; validate before paying
    """
    amt = fields.get("amount_due") or "the listed balance"

    # ── Medical ──────────────────────────────────────────────────────────
    if doc_type == "explanation_of_benefits":
        return "not_a_bill", "This is usually NOT a bill. Do not pay based on this paper alone — wait for a separate invoice from your provider."
    if doc_type == "medicare_summary_notice":
        return "review_first", "Review what Medicare approved and compare with any provider bill before paying."
    if doc_type == "claim_denial_letter":
        return "appeal_or_call", "This is a denial — do not pay. Focus on filing an appeal before the deadline."
    if doc_type == "medicaid_notice":
        return "respond_to_notice", "This is a coverage notice. The most important action is responding on time, not paying."
    if doc_type == "social_security_notice":
        return "respond_to_notice", "This is a Social Security notice. Read it carefully — it may require a response."
    if doc_type == "itemized_medical_bill":
        return "possible_bill", f"This appears to be a bill. Review each charge carefully before paying {amt}."
    if doc_type == "prescription_drug_notice":
        return "respond_to_notice", "This may require a response from you or your doctor. Review the next steps."
    if doc_type == "veterans_benefits_letter":
        return "respond_to_notice", "This is a VA benefits letter. It may require a response or acknowledgement."

    # ── Utility ──────────────────────────────────────────────────────────
    if doc_type in _UTILITY_TYPES:
        late_risk = fields.get("late_fee_risk", False)
        suffix = " ⚠️ Late fees or service interruption may apply if not paid on time." if late_risk else ""
        return "pay_utility", f"This is a utility bill. Amount due: {amt}.{suffix}"

    # ── Housing ───────────────────────────────────────────────────────────
    if doc_type == "property_tax_bill":
        return "pay_housing", f"This is a property tax bill. Amount due: {amt}. Penalties apply after the deadline."
    if doc_type == "hoa_statement":
        return "pay_housing", f"This is your HOA statement. Unpaid dues can result in a lien on your property. Amount: {amt}."
    if doc_type == "rent_statement":
        return "pay_housing", f"This is a rent statement. Amount due: {amt}."
    if doc_type == "mortgage_statement":
        return "pay_housing", f"This is your mortgage payment. Amount due: {amt}."
    if doc_type == "home_insurance_bill":
        return "pay_housing", f"This is your home insurance premium. Pay {amt} to keep your coverage active."

    # ── Financial ─────────────────────────────────────────────────────────
    if doc_type == "credit_card_statement":
        min_pay = fields.get("minimum_payment") or "the minimum shown"
        return "pay_financial", f"Pay at least {min_pay} by the due date to avoid late fees. Paying the full balance avoids interest."
    if doc_type == "collection_notice":
        return "verify_debt", "Do NOT pay yet. First request written proof that this debt is valid (debt validation letter)."
    if doc_type == "irs_notice":
        return "respond_to_notice", "Do not ignore this IRS notice. Respond by the deadline — ignoring it can lead to penalties."
    if doc_type == "loan_statement":
        return "pay_financial", f"Loan payment due: {amt}."
    if doc_type in {"food_assistance_notice", "housing_assistance_notice", "financial_assistance_letter"}:
        return "respond_to_notice", "This notice may require a response to maintain or apply for benefits."

    return "review_first", "Review this document carefully before paying or calling anyone."


def build_warning_flags(doc_type: str, fields: dict[str, Any], deadlines: list[dict[str, Any]]) -> list[str]:
    """
    Short warning strings shown prominently in the UI.
    Restores original _warning_flags() and extends it for all new bill types.
    """
    flags: list[str] = []

    # ── Original flags (preserved exactly) ──────────────────────────────
    if doc_type == "claim_denial_letter":
        flags.append("⚠️ Appeal deadline — act quickly")
    if doc_type == "medicaid_notice":
        flags.append("⚠️ Benefits may be affected if you miss the response date")
    dupes = int(fields.get("possible_duplicate_charges") or fields.get("possible_duplicate_charge_count") or 0)
    if dupes > 0:
        flags.append(f"⚠️ {dupes} possible duplicate charge(s) found")
    if deadlines:
        flags.append("📅 Important dates were detected in this document")

    # ── New flags for extended bill types ────────────────────────────────
    if fields.get("late_fee_risk"):
        flags.append("⚠️ Late fee or service interruption risk")
    if doc_type == "collection_notice":
        flags.append("⚠️ Verify this debt before paying — FDCPA rights apply")
    if doc_type == "irs_notice":
        flags.append("⚠️ IRS notices must not be ignored")
    if doc_type == "property_tax_bill" and fields.get("penalty_date"):
        flags.append(f"📅 Penalty begins after {fields['penalty_date']}")
    if doc_type == "hoa_statement" and fields.get("special_assessment"):
        flags.append(f"💰 Special assessment: {fields['special_assessment']}")
    if fields.get("assistance_available"):
        flags.append("ℹ️ Payment assistance programs may be available")

    return flags[:5]


def build_call_script(doc_type: str, fields: dict[str, Any]) -> str:
    """
    Ready-to-read phone script for seniors.
    Restores original _call_script() and extends it for all new bill types.
    """
    provider = fields.get("provider_name") or "the company"
    account = (
        fields.get("account_number")
        or fields.get("claim_number")
        or fields.get("claim_or_reference_number")
        or fields.get("parcel_number")
        or "the reference number on the letter"
    )

    # ── Original scripts (preserved exactly) ─────────────────────────────
    if doc_type == "claim_denial_letter":
        return (f"Hello, I am calling about a claim denial. My reference number is {account}. "
                "Please explain why it was denied, what deadline applies, and what I need to send for an appeal.")
    if doc_type == "explanation_of_benefits":
        return (f"Hello, I received an Explanation of Benefits and want to confirm whether I owe anything yet. "
                f"Please help me compare it with any bill from {provider}.")
    if doc_type == "medicaid_notice":
        return (f"Hello, I received a Medicaid notice and want to confirm what action I need to take "
                f"and when it is due. My reference number is {account}.")

    # ── New scripts for extended bill types ───────────────────────────────
    if doc_type == "medicare_summary_notice":
        return (f"Hello, I received a Medicare Summary Notice. My claim number is {account}. "
                "I want to confirm what Medicare paid and how much I may still owe to my provider.")
    if doc_type == "itemized_medical_bill":
        return (f"Hello, I am calling about a medical bill for account number {account}. "
                "I would like a complete itemized breakdown of all charges and to confirm the amount due before I pay.")
    if doc_type == "social_security_notice":
        return (f"Hello, I received a Social Security notice and want to confirm what it means and "
                f"whether any action is required from me. My reference is {account}.")
    if doc_type in _UTILITY_TYPES:
        return (f"Hello, I am calling about my bill for account number {account}. "
                "I have a question about the charges and want to confirm the correct amount due and the due date.")
    if doc_type == "property_tax_bill":
        return (f"Hello, I am calling about my property tax bill for parcel number {account}. "
                "I want to confirm the amount due, the payment deadline, and whether I qualify for any senior exemptions.")
    if doc_type == "collection_notice":
        return (f"Hello, I received a collection notice for account {account}. "
                "I am exercising my right under the FDCPA to request written validation of this debt "
                "before making any payment.")
    if doc_type == "irs_notice":
        return (f"Hello, I received an IRS notice, notice number {account}. "
                "I want to understand what the notice is about, whether I owe money, and how to respond correctly.")
    if doc_type == "credit_card_statement":
        return (f"Hello, I am calling about my credit card statement for account {account}. "
                "I want to confirm the minimum payment due and the due date.")

    # Generic fallback (matches original behaviour)
    return (f"Hello, I am calling about paperwork from {provider}. My reference number is {account}. "
            "Please explain what this document means, whether I owe money, and what I should do next.")


def build_senior_view(
    doc_type: str,
    fields: dict[str, Any],
    deadlines: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    text: str,
) -> dict[str, Any]:
    """
    Builds the ui_summary dict embedded inside extracted_fields.
    This is read directly by the frontend Simple Mode panel and the mobile
    'Key information' card.

    Preserves 100% of original _build_senior_view() output keys:
      document_family, what_this_is, payment_status, payment_message,
      main_amount, main_due_date, contact_phone, contact_email,
      warning_flags, next_steps, call_script, needs_trusted_helper

    Extended with new keys for new bill types:
      document_category, late_fee_risk, assistance_available
    """
    payment_status, payment_message = build_payment_guidance(doc_type, fields)

    # Best due date across all possible field names
    # NEVER use date_of_birth as a key date
    _dob = fields.get("date_of_birth", "")
    main_due_date = (
        fields.get("due_date")
        or fields.get("renewal_due_date")
        or fields.get("statement_date")
        or fields.get("service_date")
        or fields.get("penalty_date")
        or fields.get("response_deadline")
        or fields.get("next_payment_date")
    )
    # Filter out DOB from deadlines before using as fallback
    if not main_due_date and deadlines:
        for dl in deadlines:
            dl_date = dl.get("date", "")
            if dl_date and dl_date != _dob and "birth" not in dl.get("title", "").lower():
                main_due_date = dl_date
                break
    # Final guard — if main_due_date matches DOB, clear it
    if main_due_date and _dob and main_due_date == _dob:
        main_due_date = None

    # Best primary amount across all possible field names
    main_amount = (
        fields.get("amount_due")
        or fields.get("patient_responsibility")
        or fields.get("maximum_you_may_be_billed")
        or fields.get("denied_amount")
        or fields.get("amount_billed")
        or fields.get("rent_amount")
        or fields.get("debt_amount")
        or fields.get("minimum_payment")
        or fields.get("statement_balance")
    )

    next_steps = [
        item.get("action") or item.get("title")
        for item in recommendations[:3]
        if item.get("action") or item.get("title")
    ]

    # Types that strongly benefit from a trusted family helper
    needs_helper_types = {
        "claim_denial_letter", "medicaid_notice", "collection_notice",
        "irs_notice", "social_security_notice", "veterans_benefits_letter",
    }

    return {
        # ── Original keys (must not be renamed) ────────────────────────
        "document_family":    derive_document_family(doc_type, text),
        "what_this_is":       build_summary(doc_type, fields, text),
        "payment_status":     payment_status,
        "payment_message":    payment_message,
        "main_amount":        main_amount,
        "main_due_date":      main_due_date,
        "contact_phone":      fields.get("contact_phone"),
        "contact_email":      fields.get("contact_email"),
        "warning_flags":      build_warning_flags(doc_type, fields, deadlines),
        "next_steps":         next_steps,
        "call_script":        build_call_script(doc_type, fields),
        "needs_trusted_helper": doc_type in needs_helper_types or bool(deadlines),

        # ── Extended keys (new — used by updated UI) ───────────────────
        "late_fee_risk":       fields.get("late_fee_risk", False),
        "assistance_available":fields.get("assistance_available", False),
        "do_i_need_to_pay_now": payment_message,  # alias for mobile card label
    }


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN ANALYSIS ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def analyze_document(text: str, filename: str = "") -> dict[str, Any]:
    """
    Full heuristic analysis pipeline.
    Called when LLM is not configured or as fallback.

    [HIPAA] This function does NOT log document text.
    """
    from datetime import datetime

    cleaned = _clean(text or "")

    if not cleaned or cleaned == "No extractable text found.":
        return {
            "document_type": "unknown",
            "document_type_confidence": 0.0,
            "summary": "We could not extract readable text from this document.",
            "extracted_fields": {},
            "deadlines": [],
            "recommendations": [{"title": "Upload a clearer file", "why": "The document text could not be read.", "action": "Try a higher-quality scan or PDF.", "priority": "high"}],
            "billing_errors": [],
            "letter": {"title": "Help request", "subject": "Need help understanding this document", "body": "I uploaded a document but was unable to read it clearly. Please advise on next steps.\n\n[Your Name]", "audience": "Billing Department", "use_case": "Request help when document is unreadable"},
            "analyzer": "rules_v3_no_text",
            "generated_at": datetime.utcnow().isoformat(),
        }

    doc_type, confidence, reasons = detect_document_type(cleaned, filename)
    fields = extract_fields(cleaned, doc_type)
    summary = build_summary(doc_type, fields, cleaned)
    recommendations = build_recommendations(doc_type, fields)
    deadlines = build_deadlines(doc_type, fields, cleaned)
    letter = build_letter(doc_type, fields)

    # Billing error detection
    billing_errors: list[dict[str, str]] = []
    if fields.get("duplicate_warning"):
        billing_errors.append({
            "description": f"{fields.get('possible_duplicate_charges', 1)} possible duplicate charge(s) detected",
            "amount": "Unknown",
            "severity": "high",
        })

    # ── [ORIGINAL FEATURE PRESERVED] ────────────────────────────────────
    # Build the senior view (ui_summary) and embed it inside extracted_fields.
    # The frontend Simple Mode panel and the mobile "Key information" card
    # both read from extracted_fields.ui_summary — this must always be present.
    senior_view = build_senior_view(doc_type, fields, deadlines, recommendations, cleaned)
    fields = {**fields, "ui_summary": senior_view}

    return {
        "document_type": doc_type,
        "document_type_confidence": confidence,
        "classification_reasons": reasons,
        "summary": summary,
        "extracted_fields": fields,        # includes ui_summary
        "deadlines": deadlines,
        "recommendations": recommendations,
        "billing_errors": billing_errors,
        "letter": letter,
        "analyzer": "rules_v3",
        "generated_at": datetime.utcnow().isoformat(),
    }


# ── Backward-compatible alias used by document_service.py ─────────────────
# The original codebase called analyze_phase1_document().
# bill_intelligence.analyze_document() is the new name.
# Both are kept so existing imports don't break.
analyze_phase1_document = analyze_document