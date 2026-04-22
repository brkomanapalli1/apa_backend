"""
scam_detection.py — AI-powered scam and fraud detection for seniors.

Phase 2 feature from the APA roadmap.

Detects patterns commonly found in:
  - Fake IRS notices
  - Medicare/insurance fraud letters
  - Gift card payment scams
  - Phishing bank messages
  - Fake subscription renewals
  - Grandparent scams
  - Lottery/prize scams
  - Tech support scams
  - Government impersonation

[HIPAA] This service processes documents that may contain PHI.
Results are stored in the audit log.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScamSignal:
    """A single scam indicator found in a document."""
    category: str
    description: str
    severity: str  # "high" | "medium" | "low"
    matched_text: str = ""


@dataclass
class ScamAnalysisResult:
    """Result of scam analysis on a document."""
    is_suspicious: bool
    confidence: float           # 0.0 to 1.0
    risk_level: str             # "high" | "medium" | "low" | "none"
    signals: list[ScamSignal] = field(default_factory=list)
    warning_message: str = ""
    safe_message: str = ""
    recommended_actions: list[str] = field(default_factory=list)
    report_url: str = "https://reportfraud.ftc.gov"
    irs_url: str = "https://www.irs.gov/individuals/how-do-you-report-suspected-tax-fraud-activity"


# ── Scam Pattern Definitions ──────────────────────────────────────────────

_HIGH_SEVERITY_PATTERNS = [
    # Gift card payment requests — extremely common senior scam
    (r"\b(?:buy|purchase|send|pay(?:ment)?)\b.{0,50}\b(?:gift\s+card|itunes|google\s+play|amazon|steam)\b",
     "gift_card_payment", "Requesting payment via gift cards — this is a classic scam tactic"),

    # Immediate arrest/legal threat
    (r"\b(?:arrest\s+warrant|federal\s+agents?|police\s+officer|sheriff|marshal)\b.{0,100}\b(?:arrest|jail|prison|crime|warrant)\b",
     "arrest_threat", "Threatening arrest — government agencies do not make arrest threats by phone or mail"),

    # Fake IRS — gift card demand
    (r"(?:irs|internal\s+revenue).{0,100}(?:gift\s+card|wire\s+transfer|cryptocurrency|bitcoin)",
     "fake_irs_payment", "IRS never requests payment via gift cards, wire transfers, or cryptocurrency"),

    # Social Security suspension scam
    (r"\b(?:social\s+security)\b.{0,100}\b(?:suspend(?:ed)?|terminat(?:ed)?|cancel(?:led)?|revok(?:ed)?)\b",
     "ssa_suspension", "Social Security Administration does not threaten to suspend benefits by mail"),

    # Medicare fraud — asking for card number
    (r"\b(?:medicare)\b.{0,100}\b(?:card\s+number|beneficiary\s+number|new\s+card|free\s+brace|free\s+equipment)\b",
     "medicare_fraud", "Requests for Medicare card numbers or free equipment may indicate Medicare fraud"),

    # Lottery/prize scam
    (r"\b(?:won|winner|selected|chosen|congratulations)\b.{0,100}\b(?:lottery|sweepstakes|prize|reward|cash)\b.{0,100}\b(?:pay|fee|tax|processing|claim)\b",
     "lottery_scam", "Lottery scam pattern detected — legitimate prizes do not require upfront fees"),

    # Virus/tech support scam
    (r"\b(?:computer|device|virus|malware|hacked|compromised)\b.{0,100}\b(?:call\s+now|immediate|technician|support)\b.{0,100}\b(?:toll.?free|\d{3}[-.\s]?\d{3}[-.\s]?\d{4})\b",
     "tech_support_scam", "Tech support scam pattern — do not call phone numbers in unsolicited messages"),
]

_MEDIUM_SEVERITY_PATTERNS = [
    # Urgency language
    (r"\b(?:act\s+now|immediate(?:ly)?|urgent|final\s+notice|last\s+chance|expires?\s+(?:today|tonight|this\s+week))\b",
     "false_urgency", "Uses false urgency — a pressure tactic common in scam documents"),

    # Threatening language
    (r"\b(?:penalty|fine|lawsuit|legal\s+action|court|seized|frozen|suspended|terminated)\b.{0,50}\b(?:failure\s+to|if\s+you\s+(?:don|do\s+not|fail))\b",
     "threat_language", "Contains threatening language — verify with the agency directly before responding"),

    # Unusual payment methods
    (r"\b(?:wire\s+transfer|western\s+union|moneygram|cryptocurrency|bitcoin|zelle|venmo|cashapp)\b",
     "suspicious_payment", "Requests unusual payment method — government agencies use checks or official billing"),

    # Fake government branding
    (r"\b(?:department\s+of\s+treasury|u\.?s\.?\s+government|federal\s+bureau|homeland\s+security)\b.{0,200}\b(?:send|pay|call|respond\s+immediately)\b",
     "government_impersonation", "May be impersonating a government agency — verify independently"),

    # Personal information request
    (r"\b(?:confirm|verify|provide|update)\b.{0,50}\b(?:social\s+security|bank\s+account|routing\s+number|pin|password|mother.?s\s+maiden)\b",
     "personal_info_request", "Requesting sensitive personal information — legitimate agencies rarely ask this by mail"),

    # Fake refund/overpayment
    (r"\b(?:refund|overpayment|unclaimed|owed|entitled)\b.{0,100}\b(?:send|wire|transfer|deposit)\b.{0,50}\b(?:fee|tax|processing|insurance)\b",
     "fake_refund", "Advance fee fraud pattern — promises a refund but requires payment first"),
]

_LOW_SEVERITY_PATTERNS = [
    # Poor formatting/typos typical of scam letters
    (r"(?:[A-Z]{5,}[\s!.]+){3,}",
     "excessive_caps", "Excessive capitalization — common in unprofessional scam documents"),

    # Generic salutation
    (r"\b(?:dear\s+(?:sir|madam|customer|user|account\s+holder|valued\s+member))\b",
     "generic_salutation", "Generic salutation — legitimate agencies typically use your full name"),

    # Vague sender
    (r"\b(?:anonymous|undisclosed|private|unknown)\b.{0,30}\b(?:sender|source|agency|department)\b",
     "vague_sender", "Vague or anonymous sender — legitimate agencies clearly identify themselves"),
]

# Known legitimate IRS communication facts
_LEGITIMATE_IRS_SIGNALS = [
    "irs always sends letters via us mail",
    "irs will not call to demand immediate payment",
    "irs does not require specific payment methods",
    "irs does not threaten arrest",
]


def analyze_for_scams(text: str, document_type: str = "", filename: str = "") -> ScamAnalysisResult:
    """
    Analyze document text for scam and fraud indicators.

    Returns a ScamAnalysisResult with confidence score and specific signals.
    Designed specifically for documents seniors commonly receive.
    """
    if not text or not text.strip():
        return ScamAnalysisResult(
            is_suspicious=False, confidence=0.0, risk_level="none",
            safe_message="No text to analyze.",
        )

    hay = text.lower()
    signals: list[ScamSignal] = []
    score = 0.0

    # ── Check high severity patterns ──────────────────────────────────────
    for pattern, category, description in _HIGH_SEVERITY_PATTERNS:
        m = re.search(pattern, hay, re.IGNORECASE | re.DOTALL)
        if m:
            signals.append(ScamSignal(
                category=category,
                description=description,
                severity="high",
                matched_text=m.group(0)[:100],
            ))
            score += 0.4

    # ── Check medium severity patterns ────────────────────────────────────
    for pattern, category, description in _MEDIUM_SEVERITY_PATTERNS:
        m = re.search(pattern, hay, re.IGNORECASE | re.DOTALL)
        if m:
            signals.append(ScamSignal(
                category=category,
                description=description,
                severity="medium",
                matched_text=m.group(0)[:100],
            ))
            score += 0.2

    # ── Check low severity patterns ───────────────────────────────────────
    for pattern, category, description in _LOW_SEVERITY_PATTERNS:
        m = re.search(pattern, hay, re.IGNORECASE | re.DOTALL)
        if m:
            signals.append(ScamSignal(
                category=category,
                description=description,
                severity="low",
                matched_text=m.group(0)[:100],
            ))
            score += 0.1

    # ── Reduce score for legitimate indicators ────────────────────────────
    # Real Medicare letters usually include beneficiary ID
    if re.search(r"\b[1-9][AC-HJ-NP-RT-Y][AC-HJ-NP-RT-Y0-9]\d[AC-HJ-NP-RT-Y][AC-HJ-NP-RT-Y0-9]\d[AC-HJ-NP-RT-Y]{2}\d{2}\b", text):
        score -= 0.1  # Real Medicare ID present — less likely to be scam

    # Real IRS letters have notice numbers
    if re.search(r"\b(?:notice|cp|letter)\s+(?:cp)?\d{2,5}[a-z]?\b", hay):
        score -= 0.1

    # ── Boost for dangerous combinations ─────────────────────────────────
    signal_cats = {s.category for s in signals}
    # Gift card payment request is always high risk regardless of other signals
    if "gift_card_payment" in signal_cats:
        score = max(score, 0.7)
    # IRS + any payment method = always high risk
    if "fake_irs_payment" in signal_cats:
        score = max(score, 0.7)
    # Arrest threat = always high risk
    if "arrest_threat" in signal_cats:
        score = max(score, 0.7)
    # Medicare card number = always high risk
    if "medicare_fraud" in signal_cats:
        score = max(score, 0.7)
    # SSA suspension = always high risk
    if "ssa_suspension" in signal_cats:
        score = max(score, 0.7)
    # Lottery + fee = always high risk
    if "lottery_scam" in signal_cats:
        score = max(score, 0.7)

    # Clamp score
    confidence = min(max(score, 0.0), 1.0)

    # ── Determine risk level ──────────────────────────────────────────────
    if confidence >= 0.65:
        risk_level = "high"
    elif confidence >= 0.35:
        risk_level = "medium"
    elif confidence >= 0.15:
        risk_level = "low"
    else:
        risk_level = "none"

    is_suspicious = confidence >= 0.4

    # ── Build response messages ───────────────────────────────────────────
    warning_message = ""
    safe_message = ""
    recommended_actions = []

    if risk_level == "high":
        warning_message = (
            "⚠️ This document shows strong signs of being a SCAM. "
            "Do NOT pay anything, do NOT call any numbers in this document, "
            "and do NOT give out any personal information."
        )
        recommended_actions = [
            "Do not pay or respond to this document",
            "Do not call any phone number listed in this document",
            "Call the real agency directly using a number from their official website",
            "Report this to the FTC at reportfraud.ftc.gov",
            "Tell a trusted family member or caregiver about this",
        ]
    elif risk_level == "medium":
        warning_message = (
            "⚠️ This document has some suspicious features. "
            "Please verify it is legitimate before responding or paying."
        )
        recommended_actions = [
            "Verify the sender by calling the agency directly (use official website for number)",
            "Do not use any phone number or link provided in this document",
            "Ask a trusted family member or caregiver to review it",
            "Contact your local Senior Medicare Patrol (SMP) if Medicare-related",
        ]
    elif risk_level == "low":
        warning_message = "ℹ️ This document has minor unusual features. Please review carefully."
        recommended_actions = [
            "Compare with previous correspondence from the same agency",
            "Verify the sender's address matches the official agency address",
        ]
    else:
        safe_message = "✓ No significant scam indicators found in this document."

    # Add high-severity signal descriptions to actions
    high_signals = [s for s in signals if s.severity == "high"]
    if high_signals:
        recommended_actions.insert(0, f"Specific concern: {high_signals[0].description}")

    return ScamAnalysisResult(
        is_suspicious=is_suspicious,
        confidence=round(confidence, 3),
        risk_level=risk_level,
        signals=signals,
        warning_message=warning_message,
        safe_message=safe_message,
        recommended_actions=recommended_actions[:5],
    )


def get_scam_education_tip(scam_category: str) -> str:
    """
    Returns an educational tip about a specific scam type.
    Used in the UI to help seniors understand the risk.
    """
    tips = {
        "gift_card_payment": (
            "Real government agencies, utilities, and businesses NEVER ask you to pay "
            "with gift cards. If anyone asks you to buy gift cards to pay a bill or fine, "
            "it is always a scam."
        ),
        "fake_irs_payment": (
            "The real IRS always sends letters by mail first. They never call demanding "
            "immediate payment, and they never accept gift cards, wire transfers, or "
            "cryptocurrency. If you owe taxes, the IRS will send a letter explaining how to pay."
        ),
        "ssa_suspension": (
            "Social Security cannot suspend your benefits without sending you a letter "
            "in advance. If someone calls claiming your Social Security number is suspended, "
            "hang up and call SSA directly at 1-800-772-1213."
        ),
        "medicare_fraud": (
            "Medicare will never call you asking for your Medicare card number. "
            "They will never offer free equipment in exchange for your Medicare number. "
            "Protect your Medicare number like a credit card number."
        ),
        "arrest_threat": (
            "Government agencies do not threaten arrest by phone or mail. "
            "If you receive a threatening call or letter claiming law enforcement will "
            "arrest you unless you pay immediately, it is a scam."
        ),
        "lottery_scam": (
            "You cannot win a contest you did not enter. Legitimate sweepstakes never "
            "require you to pay fees, taxes, or processing charges to claim your prize. "
            "If it asks for money first, it is a scam."
        ),
        "tech_support_scam": (
            "Microsoft, Apple, and other companies never send unsolicited popups or "
            "letters asking you to call a number for computer help. Do not call numbers "
            "from popups or unsolicited messages."
        ),
    }
    return tips.get(scam_category, (
        "When in doubt, do not respond to suspicious mail or calls. "
        "Instead, contact the agency directly using a phone number from their "
        "official website or a previous letter you know is genuine."
    ))
