"""
medication_service.py — Medication Tracking & Reminder Extraction

Phase 2 feature from the APA roadmap.

Extracts medication instructions from:
  - Prescription paperwork
  - Hospital discharge papers
  - Doctor visit summaries
  - Pharmacy receipts

Then converts them into structured reminders:
  "Take 1 tablet twice daily after meals"
  → Morning reminder (8:00 AM)
  → Evening reminder (6:00 PM)

[HIPAA] Medication data is PHI. All access is logged.
Drug interaction warnings are informational only — not medical advice.
Always instructs users to consult their pharmacist or doctor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MedicationEntry:
    """A single medication extracted from a document."""
    name: str
    dosage: str | None = None
    frequency: str | None = None
    timing: list[str] = field(default_factory=list)  # ["morning", "evening"]
    with_food: bool | None = None
    refill_date: str | None = None
    prescriber: str | None = None
    pharmacy: str | None = None
    instructions: str = ""
    warnings: list[str] = field(default_factory=list)
    reminder_times: list[str] = field(default_factory=list)  # ["08:00", "20:00"]


@dataclass
class MedicationExtractionResult:
    """Result of medication extraction from a document."""
    medications: list[MedicationEntry]
    has_medications: bool
    discharge_instructions: list[str] = field(default_factory=list)
    follow_up_appointments: list[str] = field(default_factory=list)
    warning_symptoms: list[str] = field(default_factory=list)
    dietary_restrictions: list[str] = field(default_factory=list)
    disclaimer: str = (
        "This information is extracted for reminder purposes only. "
        "Always follow your doctor's or pharmacist's exact instructions. "
        "This is not medical advice."
    )


# ── Frequency → Reminder Time Mapping ────────────────────────────────────

_FREQUENCY_TO_TIMES = {
    "once daily": ["08:00"],
    "once a day": ["08:00"],
    "qd": ["08:00"],
    "every day": ["08:00"],
    "twice daily": ["08:00", "20:00"],
    "twice a day": ["08:00", "20:00"],
    "bid": ["08:00", "20:00"],
    "two times daily": ["08:00", "20:00"],
    "three times daily": ["08:00", "14:00", "20:00"],
    "three times a day": ["08:00", "14:00", "20:00"],
    "tid": ["08:00", "14:00", "20:00"],
    "four times daily": ["08:00", "12:00", "16:00", "20:00"],
    "four times a day": ["08:00", "12:00", "16:00", "20:00"],
    "qid": ["08:00", "12:00", "16:00", "20:00"],
    "every 4 hours": ["08:00", "12:00", "16:00", "20:00", "00:00"],
    "every 6 hours": ["06:00", "12:00", "18:00", "00:00"],
    "every 8 hours": ["08:00", "16:00", "00:00"],
    "every 12 hours": ["08:00", "20:00"],
    "every other day": ["08:00"],
    "weekly": ["08:00"],
    "as needed": [],
    "prn": [],
}

# ── Medication Name Extraction Patterns ───────────────────────────────────

_MED_PATTERNS = [
    # "Take [drug] [dosage]"
    r"(?:take|start|begin|continue)\s+([A-Za-z][A-Za-z\s\-]+(?:\s+\d+\s*(?:mg|mcg|ml|g|units?))?)(?:\s+(?:\d+\s+)?tablet|capsule|pill|dose)?",
    # "[Drug] [dosage] [frequency]"
    r"([A-Za-z][a-z]+(?:in|ol|pril|sartan|statin|vir|mab|tide|ine|ate|ase)?)\s+(\d+\s*(?:mg|mcg|ml|g|units?))",
    # "Prescription: [Drug]"
    r"(?:prescription|rx|medication|drug|medicine):\s*([A-Za-z][A-Za-z\s\-]+)",
    # Common prescription header format
    r"^([A-Z][a-z]+(?:in|ol|pril|ine|ate|mab)?)\s+\d+\s*(?:mg|mcg|ml)",
]

# Known common medications for seniors (helps with name extraction accuracy)
_COMMON_SENIOR_MEDS = {
    "metformin", "lisinopril", "atorvastatin", "amlodipine", "metoprolol",
    "omeprazole", "simvastatin", "losartan", "gabapentin", "hydrochlorothiazide",
    "levothyroxine", "furosemide", "warfarin", "aspirin", "clopidogrel",
    "pantoprazole", "atenolol", "carvedilol", "spironolactone", "digoxin",
    "glipizide", "glimepiride", "insulin", "prednisone", "albuterol",
    "sertraline", "escitalopram", "donepezil", "memantine", "rivastigmine",
    "alendronate", "calcium", "vitamin d", "vitamin b12", "folic acid",
    "potassium", "ferrous sulfate", "tamsulosin", "finasteride", "oxybutynin",
}

# Timing keywords
_TIMING_PATTERNS = {
    "morning": r"\b(?:morning|breakfast|am|wake(?:\s+up)?)\b",
    "noon": r"\b(?:noon|lunch|midday)\b",
    "evening": r"\b(?:evening|dinner|supper|pm)\b",
    "bedtime": r"\b(?:bedtime|sleep|night|hs)\b",
    "with_food": r"\b(?:with\s+food|after\s+(?:meal|breakfast|lunch|dinner)|with\s+meal)\b",
    "without_food": r"\b(?:without\s+food|on\s+empty\s+stomach|before\s+(?:meal|food|breakfast))\b",
}

# Warning symptom patterns (from discharge papers)
_WARNING_SYMPTOM_PATTERNS = [
    r"(?:call|contact|seek|go\s+to).{0,50}(?:if|when|should).{0,100}(?:chest\s+pain|difficulty\s+breathing|shortness\s+of\s+breath)",
    r"(?:warning|watch\s+for|signs\s+of).{0,200}(?:bleeding|bruising|dizziness|confusion|swelling)",
    r"(?:emergency|911|er|emergency\s+room).{0,100}(?:if|when)",
]

# Dietary restriction patterns
_DIETARY_PATTERNS = [
    r"(?:avoid|do\s+not\s+eat|limit|restrict).{0,100}(?:grapefruit|alcohol|salt|sodium|potassium|vitamin\s+k|dairy)",
    r"(?:low\s+sodium|low\s+salt|low\s+fat|diabetic|renal|cardiac)\s+diet",
    r"(?:drink\s+plenty\s+of\s+water|stay\s+hydrated|increase\s+fluid)",
]


def extract_medications(text: str, document_type: str = "") -> MedicationExtractionResult:
    """
    Extract medication information from document text.

    Works with:
    - Prescription labels and paperwork
    - Hospital discharge instructions
    - Doctor visit summaries
    - Pharmacy receipts
    """
    if not text or not text.strip():
        return MedicationExtractionResult(medications=[], has_medications=False)

    medications: list[MedicationEntry] = []
    discharge_instructions: list[str] = []
    follow_up_appointments: list[str] = []
    warning_symptoms: list[str] = []
    dietary_restrictions: list[str] = []

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    hay = text.lower()

    # ── Extract individual medications ────────────────────────────────────
    # First try known medication names
    for med_name in _COMMON_SENIOR_MEDS:
        if re.search(rf"\b{re.escape(med_name)}\b", hay):
            entry = _extract_med_details(text, med_name)
            if entry:
                medications.append(entry)

    # Try pattern-based extraction for unknown medications
    for pattern in _MED_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
            name = m.group(1).strip().lower()
            # Skip if already found or too short/generic
            if len(name) < 4 or name in ("take", "start", "use", "apply"):
                continue
            if not any(med.name.lower() == name for med in medications):
                entry = _extract_med_details(text, name)
                if entry:
                    medications.append(entry)

    # ── Extract discharge/follow-up info ─────────────────────────────────
    for line in lines:
        lower = line.lower()

        # Follow-up appointments
        if re.search(r"\b(?:follow.?up|appointment|see\s+(?:your\s+)?(?:doctor|physician|specialist))\b", lower):
            if re.search(r"\b(?:days?|weeks?|months?|\d+)\b", lower):
                follow_up_appointments.append(line[:200])

        # Warning symptoms (from discharge papers)
        for pattern in _WARNING_SYMPTOM_PATTERNS:
            if re.search(pattern, lower):
                warning_symptoms.append(line[:200])
                break

        # Dietary restrictions
        for pattern in _DIETARY_PATTERNS:
            if re.search(pattern, lower):
                dietary_restrictions.append(line[:200])
                break

    # ── General discharge instructions ───────────────────────────────────
    discharge_markers = ["activity restriction", "wound care", "incision", "bandage",
                         "dressing change", "keep dry", "no driving", "no lifting",
                         "bed rest", "elevate", "ice pack"]
    for line in lines:
        if any(marker in line.lower() for marker in discharge_markers):
            discharge_instructions.append(line[:200])

    return MedicationExtractionResult(
        medications=medications[:20],  # Cap at 20 medications
        has_medications=bool(medications),
        discharge_instructions=discharge_instructions[:10],
        follow_up_appointments=follow_up_appointments[:5],
        warning_symptoms=warning_symptoms[:5],
        dietary_restrictions=dietary_restrictions[:5],
    )


def _extract_med_details(text: str, med_name: str) -> MedicationEntry | None:
    """Extract details for a specific medication from surrounding text."""
    # Find the context around the medication name
    pattern = re.compile(rf".{{0,200}}\b{re.escape(med_name)}\b.{{0,300}}", re.IGNORECASE | re.DOTALL)
    m = pattern.search(text)
    if not m:
        return None

    context = m.group(0)
    context_lower = context.lower()

    entry = MedicationEntry(name=med_name.title())

    # Extract dosage
    dosage_m = re.search(r"(\d+(?:\.\d+)?\s*(?:mg|mcg|ml|g|units?|iu))", context, re.IGNORECASE)
    if dosage_m:
        entry.dosage = dosage_m.group(1)

    # Extract frequency
    for freq_text, times in _FREQUENCY_TO_TIMES.items():
        if freq_text in context_lower:
            entry.frequency = freq_text
            entry.reminder_times = times.copy()
            break

    # Extract timing
    for timing_name, timing_pattern in _TIMING_PATTERNS.items():
        if re.search(timing_pattern, context_lower):
            if timing_name == "with_food":
                entry.with_food = True
            elif timing_name == "without_food":
                entry.with_food = False
            else:
                if timing_name not in entry.timing:
                    entry.timing.append(timing_name)

    # Extract refill date
    refill_m = re.search(
        r"(?:refill|expires?|valid\s+until|fill\s+by).{0,30}(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})",
        context, re.IGNORECASE
    )
    if refill_m:
        entry.refill_date = refill_m.group(1)

    # Build instruction string
    parts = []
    if entry.dosage:
        parts.append(entry.dosage)
    if entry.frequency:
        parts.append(entry.frequency)
    if entry.with_food is True:
        parts.append("with food")
    elif entry.with_food is False:
        parts.append("on empty stomach")
    if parts:
        entry.instructions = f"Take {' '.join(parts)}"

    return entry


def format_medication_reminders(medications: list[MedicationEntry]) -> list[dict[str, Any]]:
    """
    Convert extracted medications into a reminder schedule.
    Returns a list of reminder objects ready for the reminder service.
    """
    reminders = []
    for med in medications:
        if not med.reminder_times:
            continue
        for time_str in med.reminder_times:
            reminders.append({
                "medication_name": med.name,
                "dosage": med.dosage,
                "time": time_str,
                "instruction": med.instructions or f"Take {med.name}",
                "with_food": med.with_food,
                "refill_date": med.refill_date,
            })
    return reminders


def generate_medication_schedule(medications: list[MedicationEntry]) -> dict[str, list[dict]]:
    """
    Generate a daily medication schedule grouped by time of day.
    Returns {"morning": [...], "noon": [...], "evening": [...], "bedtime": [...]}
    """
    schedule: dict[str, list[dict]] = {
        "morning": [],
        "noon": [],
        "afternoon": [],
        "evening": [],
        "bedtime": [],
        "as_needed": [],
    }

    time_to_slot = {
        "06:00": "morning", "07:00": "morning", "08:00": "morning", "09:00": "morning",
        "10:00": "morning", "11:00": "morning",
        "12:00": "noon", "13:00": "noon",
        "14:00": "afternoon", "15:00": "afternoon", "16:00": "afternoon",
        "17:00": "evening", "18:00": "evening", "19:00": "evening", "20:00": "evening",
        "21:00": "bedtime", "22:00": "bedtime", "23:00": "bedtime", "00:00": "bedtime",
    }

    for med in medications:
        if not med.reminder_times:
            schedule["as_needed"].append({
                "name": med.name,
                "dosage": med.dosage,
                "instruction": med.instructions or f"Take {med.name} as needed",
            })
            continue

        for time_str in med.reminder_times:
            slot = time_to_slot.get(time_str, "morning")
            schedule[slot].append({
                "name": med.name,
                "dosage": med.dosage,
                "time": time_str,
                "instruction": med.instructions or f"Take {med.name}",
                "with_food": med.with_food,
            })

    # Remove empty slots
    return {k: v for k, v in schedule.items() if v}
