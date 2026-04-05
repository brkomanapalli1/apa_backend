from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from openai import OpenAI

from app.core.config import settings

PHASE1_PROMPT = """You are a paperwork assistant for older adults.
Analyze the uploaded document and return strict JSON with these keys:
- document_type: one of medicare_summary_notice, explanation_of_benefits, claim_denial_letter, itemized_medical_bill, medicaid_notice, unknown
- document_type_confidence: number from 0 to 1
- summary: concise plain-English explanation for a senior or trusted helper
- extracted_fields: object with the most relevant structured facts from the document
- deadlines: array of objects with keys title, date, reason, action
- recommendations: array of objects with keys title, why, priority, action
- letter: object with keys title, subject, body, audience, use_case
Keep the guidance practical. If the document is an EOB, clearly say it is not a bill.
If the document looks like a denial, include appeal-oriented next steps.
"""

MONEY_RE = re.compile(r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?")
DATE_RE = re.compile(
    r"\b(?:\d{1,2}/\d{1,2}/\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s+\d{4})\b",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _excerpt(text: str, limit: int = 8000) -> str:
    return (text or "")[:limit]


def _money_values(text: str) -> list[str]:
    seen: list[str] = []
    for match in MONEY_RE.findall(text or ""):
        if match not in seen:
            seen.append(match)
    return seen


def _first_label_amount(text: str, labels: list[str]) -> str | None:
    for label in labels:
        pattern = re.compile(rf"{re.escape(label)}[^\n$]*({MONEY_RE.pattern})", re.IGNORECASE)
        match = pattern.search(text or "")
        if match:
            return match.group(1)
    return None


def _first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE | re.MULTILINE)
        if match:
            return _clean(match.group(1))
    return None


def detect_document_type(text: str, filename: str = "") -> tuple[str, float, list[str]]:
    hay = f"{filename}\n{text}".lower()
    reasons: list[str] = []

    if "medicare summary notice" in hay or re.search(r"\bmsn\b", hay):
        reasons.append("Found Medicare Summary Notice terminology")
        return "medicare_summary_notice", 0.97, reasons
    if "explanation of benefits" in hay or re.search(r"\beob\b", hay):
        reasons.append("Found Explanation of Benefits terminology")
        return "explanation_of_benefits", 0.96, reasons
    if any(token in hay for token in ["claim denied", "denial", "adverse determination", "appeal rights", "not medically necessary"]):
        reasons.append("Found denial and appeal language")
        return "claim_denial_letter", 0.92, reasons
    if any(token in hay for token in ["itemized bill", "amount due", "statement date", "balance due", "patient account"]) and len(_money_values(hay)) >= 2:
        reasons.append("Found billing language and multiple monetary amounts")
        return "itemized_medical_bill", 0.88, reasons
    if "medicaid" in hay or any(token in hay for token in ["renew your benefits", "coverage ending", "eligibility notice"]):
        reasons.append("Found Medicaid or eligibility notice language")
        return "medicaid_notice", 0.86, reasons
    if len(_money_values(hay)) >= 3:
        reasons.append("Document contains several money amounts and may be a bill")
        return "itemized_medical_bill", 0.55, reasons

    reasons.append("No strong Medicare/Medicaid paperwork markers found")
    return "unknown", 0.35, reasons


def _extract_common_fields(text: str, document_type: str) -> dict[str, Any]:
    return {
        "document_type": document_type,
        "provider_name": _first_match(text, [
            r"(?:Provider|Hospital|Facility|Doctor)[:\s]+([^\n]{3,80})",
            r"^([A-Z][A-Za-z0-9&,.'\- ]{4,80})$",
        ]),
        "member_name": _first_match(text, [r"(?:Patient|Member|Beneficiary|Recipient)[:\s]+([^\n]{3,80})"]),
        "member_id": _first_match(text, [r"(?:Member ID|Medicare Number|Recipient ID|Claim Number)[:\s#]*([^\n]{4,80})"]),
        "service_date": _first_match(text, [r"(?:Date of Service|Service Date|From)[:\s]+([^\n]{3,60})"]),
        "contact_phone": PHONE_RE.search(text or "").group(0) if PHONE_RE.search(text or "") else None,
        "contact_email": EMAIL_RE.search(text or "").group(0) if EMAIL_RE.search(text or "") else None,
        "all_detected_amounts": _money_values(text)[:12],
    }


def _estimate_duplicate_charges(text: str) -> int:
    lines = [re.sub(r"\s+", " ", line).strip().lower() for line in (text or "").splitlines() if line.strip()]
    service_lines = [line for line in lines if MONEY_RE.search(line) and len(line) > 10]
    seen: dict[str, int] = {}
    dupes = 0
    for line in service_lines:
        normalized = re.sub(MONEY_RE.pattern, "$AMOUNT", line)
        seen[normalized] = seen.get(normalized, 0) + 1
        if seen[normalized] == 2:
            dupes += 1
    return dupes


def _extract_fields(text: str, document_type: str) -> dict[str, Any]:
    fields = _extract_common_fields(text, document_type)

    if document_type == "medicare_summary_notice":
        fields.update({
            "total_amount_billed": _first_label_amount(text, ["total amount billed", "provider billed", "amount billed"]),
            "medicare_approved_amount": _first_label_amount(text, ["medicare approved", "approved amount"]),
            "medicare_paid_amount": _first_label_amount(text, ["medicare paid", "amount medicare paid"]),
            "maximum_you_may_be_billed": _first_label_amount(text, ["maximum you may be billed", "you may be billed", "patient responsibility"]),
            "claim_number": _first_match(text, [r"(?:Claim Number|Claim No\.)[:\s#]*([^\n]{3,80})"]),
        })
    elif document_type == "explanation_of_benefits":
        fields.update({
            "plan_name": _first_match(text, [r"(?:Plan|Insurance Plan)[:\s]+([^\n]{3,80})"]),
            "amount_billed": _first_label_amount(text, ["amount billed", "provider charge", "total charge"]),
            "plan_paid": _first_label_amount(text, ["plan paid", "insurance paid", "paid by plan"]),
            "patient_responsibility": _first_label_amount(text, ["patient responsibility", "you owe", "member responsibility"]),
            "network_status": _first_match(text, [r"(?:Network Status|Provider Status)[:\s]+([^\n]{3,60})"]),
            "is_bill": False,
        })
    elif document_type == "claim_denial_letter":
        fields.update({
            "denial_reason": _first_match(text, [
                r"(?:Reason for Denial|Why We Denied Your Claim|Denial Reason)[:\s]+([^\n]{8,200})",
                r"(not medically necessary[^\n]{0,160})",
            ]),
            "claim_or_reference_number": _first_match(text, [r"(?:Claim Number|Reference Number|Case Number)[:\s#]*([^\n]{3,80})"]),
            "appeal_deadline_days": _first_match(text, [r"within\s+(\d{1,3}\s+days)", r"appeal[^\n]{0,40}within\s+(\d{1,3}\s+days)"]),
            "denied_amount": _first_label_amount(text, ["denied amount", "amount denied", "amount not paid"]),
        })
    elif document_type == "itemized_medical_bill":
        fields.update({
            "statement_date": _first_match(text, [r"(?:Statement Date|Bill Date)[:\s]+([^\n]{3,60})"]),
            "account_number": _first_match(text, [r"(?:Account Number|Account No\.)[:\s#]*([^\n]{3,80})"]),
            "amount_due": _first_label_amount(text, ["amount due", "balance due", "total due", "patient due"]),
            "total_charges": _first_label_amount(text, ["total charges", "total amount billed", "charges"]),
            "possible_duplicate_charge_count": _estimate_duplicate_charges(text),
        })
    elif document_type == "medicaid_notice":
        fields.update({
            "program": _first_match(text, [r"(Medicaid[^\n]{0,80})"]),
            "renewal_due_date": _first_match(text, [r"(?:Renew by|Renewal Due Date|Complete by)[:\s]+([^\n]{3,60})"]),
            "coverage_status": _first_match(text, [r"(?:Coverage Status|Status)[:\s]+([^\n]{3,80})", r"(coverage (?:ending|approved|renewed)[^\n]{0,100})"]),
        })
    else:
        fields.update({"primary_amount": fields["all_detected_amounts"][0] if fields.get("all_detected_amounts") else None})

    return fields


def _build_deadlines(text: str, document_type: str, fields: dict[str, Any]) -> list[dict[str, str | None]]:
    deadlines: list[dict[str, str | None]] = []
    seen_dates: set[str] = set()

    renewal_due = fields.get("renewal_due_date")
    if document_type == "medicaid_notice" and renewal_due:
        deadlines.append({
            "title": "Medicaid renewal due",
            "date": str(renewal_due),
            "reason": "The notice appears to contain a benefits renewal deadline.",
            "action": "Submit renewal paperwork before this date to reduce the chance of a coverage gap.",
        })
        seen_dates.add(str(renewal_due))

    days_text = str(fields.get("appeal_deadline_days") or "")
    day_match = re.search(r"(\d{1,3})", days_text)
    if document_type == "claim_denial_letter" and day_match:
        days = int(day_match.group(1))
        inferred = (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()
        deadlines.append({
            "title": "Appeal deadline window",
            "date": inferred,
            "reason": f"The document says you may need to appeal within {days} days.",
            "action": "Prepare and send the appeal as soon as possible, and confirm the exact deadline with the plan or provider.",
        })
        seen_dates.add(inferred)

    for raw_date in DATE_RE.findall(text or "")[:5]:
        if raw_date in seen_dates:
            continue
        deadlines.append({
            "title": f"Important date found: {raw_date}",
            "date": raw_date,
            "reason": "A date was detected in the document and may matter for follow-up.",
            "action": "Review the nearby section to confirm what this date means.",
        })
        seen_dates.add(raw_date)

    return deadlines[:6]


def _recommendations(document_type: str, fields: dict[str, Any], text: str) -> list[dict[str, str]]:
    recs: list[dict[str, str]] = []

    if document_type == "explanation_of_benefits":
        recs.append({"title": "Do not pay this EOB by itself", "why": "An Explanation of Benefits is usually not a bill.", "priority": "high", "action": "Wait for a provider bill or compare it with the provider statement before paying anything."})
        recs.append({"title": "Compare billed, paid, and responsibility amounts", "why": "Differences between the EOB and provider bill often reveal billing errors.", "priority": "high", "action": "Match the EOB amounts against the provider invoice and ask questions about mismatches."})
    elif document_type == "medicare_summary_notice":
        recs.append({"title": "Review what Medicare approved and paid", "why": "This shows whether the provider billed more than Medicare approved.", "priority": "high", "action": "Compare the approved amount, paid amount, and patient responsibility before paying a provider bill."})
        recs.append({"title": "Check patient responsibility carefully", "why": "The 'maximum you may be billed' line is often the most important line for families.", "priority": "high", "action": "If a provider bill is higher than the patient responsibility shown here, ask the provider to correct it."})
    elif document_type == "claim_denial_letter":
        recs.append({"title": "Start the appeal quickly", "why": "Denial letters often have short appeal windows.", "priority": "high", "action": "Gather the denial reason, claim number, doctor notes, and supporting records before sending an appeal."})
        recs.append({"title": "Call the plan or provider for clarification", "why": "A denial reason can sometimes be fixed with coding corrections or missing records.", "priority": "medium", "action": "Ask exactly why the claim was denied and what documents would help reverse the decision."})
    elif document_type == "itemized_medical_bill":
        recs.append({"title": "Request or verify the itemized bill", "why": "Line-level detail helps catch duplicates and incorrect charges.", "priority": "high", "action": "Ask the provider for a full itemized statement if this document is not already itemized."})
        if int(fields.get("possible_duplicate_charge_count") or 0) > 0:
            recs.append({"title": "Review possible duplicate charges", "why": "Repeated service lines may indicate overbilling.", "priority": "high", "action": "Circle repeated charges and ask the billing office to explain or remove them."})
        recs.append({"title": "Ask about financial assistance or payment review", "why": "Hospitals often have hardship or discount programs.", "priority": "medium", "action": "Call the billing office before paying the full balance if the amount due is hard to manage."})
    elif document_type == "medicaid_notice":
        recs.append({"title": "Confirm your renewal or eligibility status", "why": "Coverage interruptions can happen when forms are late or incomplete.", "priority": "high", "action": "Complete any renewal steps and keep copies of everything you submit."})
        recs.append({"title": "Call the Medicaid office if anything is unclear", "why": "State notices vary and missing one instruction can affect coverage.", "priority": "medium", "action": "Ask which exact documents or proofs are still needed and when they are due."})
    else:
        recs.append({"title": "Review the most important dates and amounts first", "why": "Dates and balances usually drive the next action on paperwork.", "priority": "medium", "action": "Check whether this is a bill, notice, or denial before responding or paying."})

    if not fields.get("contact_phone") and "call" in (text or "").lower():
        recs.append({"title": "Find the right contact number", "why": "The next step may require calling the insurer or provider.", "priority": "low", "action": "Look for a member services or billing phone number on the document or the back page."})

    return recs[:5]


def _summary(document_type: str, fields: dict[str, Any], text: str) -> str:
    if document_type == "explanation_of_benefits":
        return (
            f"This looks like an Explanation of Benefits, which is usually not a bill. "
            f"The document shows billed amount {fields.get('amount_billed') or 'unknown'}, "
            f"plan paid {fields.get('plan_paid') or 'unknown'}, and patient responsibility {fields.get('patient_responsibility') or 'unknown'}. "
            f"Use it to compare against the provider bill before paying."
        )
    if document_type == "medicare_summary_notice":
        return (
            f"This appears to be a Medicare Summary Notice. It shows what the provider billed, what Medicare approved and paid, and what you may still owe. "
            f"Right now, billed is {fields.get('total_amount_billed') or 'unknown'}, Medicare paid {fields.get('medicare_paid_amount') or 'unknown'}, and patient responsibility is {fields.get('maximum_you_may_be_billed') or 'unknown'}."
        )
    if document_type == "claim_denial_letter":
        return (
            f"This looks like a claim denial letter. The main issue appears to be: {fields.get('denial_reason') or 'the claim was denied'}. "
            f"You should review the appeal instructions right away and gather supporting records before the deadline."
        )
    if document_type == "itemized_medical_bill":
        dupes = int(fields.get("possible_duplicate_charge_count") or 0)
        duplicate_text = f" I found about {dupes} possible duplicate charge pattern(s)." if dupes else ""
        return (
            f"This appears to be a medical bill or itemized statement. The amount due is {fields.get('amount_due') or 'unknown'}. "
            f"Review each charge before paying, especially if the bill does not match your insurance statement.{duplicate_text}"
        )
    if document_type == "medicaid_notice":
        return (
            f"This appears to be a Medicaid notice. The notice suggests coverage status is {fields.get('coverage_status') or 'unclear'}, "
            f"and the renewal or response date may be {fields.get('renewal_due_date') or 'not clearly stated'}."
        )

    excerpt = _clean(text)[:280]
    return f"This document could not be classified with high confidence. Here is the plain-English gist: {excerpt}"


def _letter(document_type: str, fields: dict[str, Any], recommendations: list[dict[str, str]], text: str) -> dict[str, str]:
    provider = fields.get("provider_name") or "Claims or Billing Department"
    member = fields.get("member_name") or "[Your Name]"
    claim_ref = fields.get("claim_number") or fields.get("claim_or_reference_number") or fields.get("account_number") or "[Claim or Account Number]"
    amount = fields.get("amount_due") or fields.get("denied_amount") or fields.get("patient_responsibility") or "[Amount]"

    if document_type == "claim_denial_letter":
        body = f"""Dear {provider},

I am writing to appeal the denial of claim/reference number {claim_ref}. According to the notice I received, the claim was denied because {fields.get('denial_reason') or '[insert denial reason]'}. I am asking for a full review of this decision.

Please review the attached records and reconsider coverage. If additional information is needed, please tell me exactly what documents are required and where they should be sent.

Patient/member name: {member}
Claim/reference number: {claim_ref}
Amount in question: {amount}

Thank you for your prompt attention.

Sincerely,
{member}
[Phone Number]
[Address]
"""
        return {"title": "Claim appeal letter draft", "subject": f"Appeal of denied claim {claim_ref}", "body": body, "audience": provider, "use_case": "Appeal a denied medical or insurance claim"}

    if document_type in {"itemized_medical_bill", "medicare_summary_notice", "explanation_of_benefits"}:
        body = f"""Dear {provider},

I am writing to dispute or request review of charges connected to account/claim number {claim_ref}. After reviewing the paperwork I received, I have questions about the amount listed as {amount} and would like a corrected itemized explanation before making payment.

Please provide:
1. A complete itemized bill or claim breakdown
2. An explanation of any charges that were denied, duplicated, or assigned to me
3. A corrected balance if any errors are found

Patient/member name: {member}
Account/claim number: {claim_ref}
Amount in question: {amount}

Please place this account on temporary hold while the charges are reviewed.

Sincerely,
{member}
[Phone Number]
[Address]
"""
        return {"title": "Billing dispute letter draft", "subject": f"Request for billing review for {claim_ref}", "body": body, "audience": provider, "use_case": "Dispute a bill or request itemized review"}

    body = f"""To whom it may concern,

I am writing because I need help understanding and resolving the attached notice. Please confirm the next steps, any documents still needed, and any deadline I must meet.

Member/recipient name: {member}
Reference number: {claim_ref}

Thank you,
{member}
[Phone Number]
"""
    return {"title": "General paperwork follow-up letter draft", "subject": "Request for clarification and next steps", "body": body, "audience": provider, "use_case": "Ask for clarification about a notice or coverage issue"}



def _derive_document_family(document_type: str, text: str) -> str:
    lowered = (text or '').lower()
    if document_type in {"medicare_summary_notice", "explanation_of_benefits", "claim_denial_letter", "itemized_medical_bill", "medicaid_notice"}:
        return "medical_or_coverage"
    if any(token in lowered for token in ["electric", "water service", "utility", "gas service"]):
        return "utility_bill"
    if any(token in lowered for token in ["collection notice", "past due", "delinquent"]):
        return "collection_notice"
    return "general_paperwork"


def _payment_guidance(document_type: str, fields: dict[str, Any]) -> tuple[str, str]:
    if document_type == "explanation_of_benefits":
        return "not_a_bill", "This is usually not a bill. Do not pay based on this paper alone."
    if document_type == "medicare_summary_notice":
        return "review_first", "Review the Medicare-approved amount and compare it with any provider bill before paying."
    if document_type == "claim_denial_letter":
        return "appeal_or_call", "This is about a denied claim, not a normal bill. Focus on appeal steps and deadlines."
    if document_type == "medicaid_notice":
        return "respond_to_notice", "This looks like a coverage or eligibility notice. The most important action is responding on time."
    if document_type == "itemized_medical_bill":
        amount = fields.get("amount_due") or "the listed balance"
        return "possible_bill", f"This appears to be a bill. Review charges and due date before paying {amount}."
    return "review_first", "Review the document carefully before paying or calling anyone."


def _warning_flags(document_type: str, fields: dict[str, Any], deadlines: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    if document_type == "claim_denial_letter":
        flags.append("Possible appeal deadline")
    if document_type == "medicaid_notice":
        flags.append("Benefits may be affected if you miss the response date")
    if int(fields.get("possible_duplicate_charge_count") or 0) > 0:
        flags.append("Possible duplicate charges found")
    if deadlines:
        flags.append("Important dates were detected")
    return flags[:4]


def _call_script(document_type: str, fields: dict[str, Any]) -> str:
    provider = fields.get("provider_name") or "your plan or provider"
    account = fields.get("account_number") or fields.get("claim_number") or fields.get("claim_or_reference_number") or "the reference number on the letter"
    if document_type == "claim_denial_letter":
        return f"Hello, I am calling about a claim denial. My reference number is {account}. Please explain why it was denied, what deadline applies, and what I need to send for an appeal."
    if document_type == "explanation_of_benefits":
        return f"Hello, I received an Explanation of Benefits and want to confirm whether I owe anything yet. Please help me compare it with any bill from {provider}."
    if document_type == "medicaid_notice":
        return f"Hello, I received a Medicaid notice and want to confirm what action I need to take and when it is due. My reference number is {account}."
    return f"Hello, I am calling about paperwork from {provider}. My reference number is {account}. Please explain what this document means, whether I owe money, and what I should do next."


def _build_senior_view(document_type: str, fields: dict[str, Any], deadlines: list[dict[str, Any]], recommendations: list[dict[str, Any]], text: str) -> dict[str, Any]:
    payment_status, payment_message = _payment_guidance(document_type, fields)
    due_date = fields.get("renewal_due_date") or fields.get("statement_date") or fields.get("service_date")
    if not due_date and deadlines:
        due_date = deadlines[0].get("date")
    next_steps = [item.get("action") or item.get("title") for item in recommendations[:3] if item.get("action") or item.get("title")]
    return {
        "document_family": _derive_document_family(document_type, text),
        "what_this_is": _summary(document_type, fields, text),
        "payment_status": payment_status,
        "payment_message": payment_message,
        "main_amount": fields.get("amount_due") or fields.get("patient_responsibility") or fields.get("maximum_you_may_be_billed") or fields.get("denied_amount") or fields.get("amount_billed"),
        "main_due_date": due_date,
        "contact_phone": fields.get("contact_phone"),
        "contact_email": fields.get("contact_email"),
        "warning_flags": _warning_flags(document_type, fields, deadlines),
        "next_steps": next_steps,
        "call_script": _call_script(document_type, fields),
        "needs_trusted_helper": document_type in {"claim_denial_letter", "medicaid_notice"} or bool(deadlines),
    }

def _heuristic_analysis(text: str, filename: str = "") -> dict[str, Any]:
    document_type, confidence, reasons = detect_document_type(text, filename)
    fields = _extract_fields(text, document_type)
    deadlines = _build_deadlines(text, document_type, fields)
    recommendations = _recommendations(document_type, fields, text)
    summary = _summary(document_type, fields, text)
    letter = _letter(document_type, fields, recommendations, text)
    senior_view = _build_senior_view(document_type, fields, deadlines, recommendations, text)
    fields = {**fields, "ui_summary": senior_view}
    return {
        "document_type": document_type,
        "document_type_confidence": confidence,
        "classification_reasons": reasons,
        "summary": summary,
        "extracted_fields": fields,
        "deadlines": deadlines,
        "recommendations": recommendations,
        "letter": letter,
        "generated_at": datetime.utcnow().isoformat(),
    }


def analyze_phase1_document(text: str, filename: str = "") -> dict[str, Any]:
    heuristic = _heuristic_analysis(text, filename)
    if settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": PHASE1_PROMPT},
                    {"role": "user", "content": _excerpt(text)},
                ],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
            parsed.setdefault("document_type", heuristic["document_type"])
            parsed.setdefault("document_type_confidence", heuristic["document_type_confidence"])
            parsed.setdefault("summary", heuristic["summary"])
            parsed.setdefault("extracted_fields", heuristic["extracted_fields"])
            parsed.setdefault("deadlines", heuristic["deadlines"])
            parsed.setdefault("recommendations", heuristic["recommendations"])
            parsed.setdefault("letter", heuristic["letter"])
            parsed["classification_reasons"] = heuristic["classification_reasons"]
            parsed["generated_at"] = datetime.utcnow().isoformat()
            return parsed
        except Exception:
            return heuristic
    return heuristic


def generate_letter_for_document(document_type: str, extracted_fields: dict[str, Any] | None, recommendations: list[dict[str, str]] | None, text: str) -> dict[str, str]:
    return _letter(document_type or "unknown", extracted_fields or {}, recommendations or [], text or "")
