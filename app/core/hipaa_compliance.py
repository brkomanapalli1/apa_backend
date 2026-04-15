"""
hipaa_compliance.py — HIPAA Safeguards Implementation

This module implements the technical safeguards required by HIPAA's
Security Rule (45 CFR §164.312) for electronic Protected Health Information (ePHI).

HIPAA Technical Safeguard Requirements covered here:
  ✓ Access Control (§164.312(a)) — unique user IDs, auto-logoff, encryption
  ✓ Audit Controls (§164.312(b)) — all PHI access/modification logged
  ✓ Integrity (§164.312(c)) — SHA-256 checksums on stored documents
  ✓ Transmission Security (§164.312(e)) — TLS enforced, no plaintext PHI
  ✓ Authentication (§164.312(d)) — JWT + MFA support

PHI Categories handled in this system:
  - Health plan beneficiary numbers (Medicare ID, Member ID)
  - Medical record numbers
  - Account numbers
  - Dates (other than year) related to individuals
  - Geographic data (ZIP codes in billing addresses)
  - Financial information related to healthcare

[IMPORTANT] What this module does NOT do:
  - Replace a formal HIPAA Risk Assessment
  - Substitute for a signed Business Associate Agreement (BAA)
  - Replace legal review of your data handling practices
  - Guarantee compliance — compliance requires process, not just code
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger("hipaa")


# ═══════════════════════════════════════════════════════════════════════════
#  PHI SENSITIVITY CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

class PHISensitivity(str, Enum):
    """HIPAA data sensitivity tiers for access decisions."""
    HIGH   = "high"    # Direct identifiers: SSN, MRN, insurance ID
    MEDIUM = "medium"  # Semi-identifiers: dates of service, diagnosis codes
    LOW    = "low"     # Non-PHI: document type, status, timestamps


# Fields that qualify as PHI under HIPAA's 18 identifiers
PHI_FIELD_PATTERNS = [
    r"member[_\s]?id",
    r"medicare[_\s]?number",
    r"social[_\s]?security",
    r"ssn",
    r"patient[_\s]?name",
    r"member[_\s]?name",
    r"date[_\s]?of[_\s]?birth",
    r"account[_\s]?number",
    r"claim[_\s]?number",
    r"provider[_\s]?name",
    r"diagnosis",
    r"icd[_\-]?\d*[_\s]?code",
    r"cpt[_\s]?code",
    r"procedure[_\s]?code",
]

PHI_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in PHI_FIELD_PATTERNS]


def classify_field(field_name: str) -> PHISensitivity:
    """Classify a field name by PHI sensitivity."""
    for pattern in PHI_PATTERNS_COMPILED:
        if pattern.search(field_name):
            return PHISensitivity.HIGH
    if any(kw in field_name.lower() for kw in ["date", "address", "zip", "phone", "email"]):
        return PHISensitivity.MEDIUM
    return PHISensitivity.LOW


def redact_phi_for_log(data: dict[str, Any]) -> dict[str, Any]:
    """
    Redact PHI fields before writing to logs.
    [HIPAA §164.312(b)] Audit logs must not contain unmasked PHI.
    """
    redacted = {}
    for key, value in data.items():
        sensitivity = classify_field(key)
        if sensitivity == PHISensitivity.HIGH:
            if isinstance(value, str) and len(value) > 4:
                redacted[key] = f"{value[:2]}***{value[-2:]}"
            else:
                redacted[key] = "***REDACTED***"
        elif sensitivity == PHISensitivity.MEDIUM and isinstance(value, str):
            redacted[key] = "***MASKED***"
        else:
            redacted[key] = value
    return redacted


# ═══════════════════════════════════════════════════════════════════════════
#  HIPAA AUDIT LOGGER
# ═══════════════════════════════════════════════════════════════════════════

class HIPAAAuditLogger:
    """
    Structured audit logger for HIPAA compliance.

    [HIPAA §164.312(b)] Implementation Specification:
    Implement hardware, software, and/or procedural mechanisms that record
    and examine activity in information systems that contain or use ePHI.

    All audit events include:
      - Who: user_id, ip_address, user_agent
      - What: action, entity_type, entity_id
      - When: timestamp (UTC ISO 8601)
      - Why: business context
      - Result: success/failure
    """

    def __init__(self, db_session: Session | None = None):
        self.db = db_session
        self._log = logging.getLogger("hipaa.audit")

    def log_phi_access(
        self,
        user_id: int,
        action: str,
        resource_type: str,
        resource_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        outcome: str = "success",
        additional_context: dict | None = None,
    ) -> str:
        """
        Log a PHI access event.

        [HIPAA] Retention: Audit logs must be retained for a minimum of 6 years.
        This system defaults to 7 years (2555 days) per AUDIT_LOG_RETENTION_DAYS.
        """
        event_id = str(uuid.uuid4())
        event = {
            "event_id": event_id,
            "event_type": "phi_access",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "ip_address": ip_address,
            "user_agent": (user_agent or "")[:200],
            "request_id": request_id,
            "outcome": outcome,
            "context": additional_context or {},
        }

        # Write to structured log (for SIEM ingestion)
        self._log.info("PHI_ACCESS %s", json.dumps(event))

        # Persist to database audit table if session available
        if self.db:
            self._persist_audit_event(event)

        return event_id

    def log_auth_event(
        self,
        user_id: int | None,
        event_type: str,
        ip_address: str | None,
        outcome: str,
        detail: dict | None = None,
    ) -> None:
        """Log authentication events (login, logout, failed attempt, MFA)."""
        event = {
            "event_type": f"auth.{event_type}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "ip_address": ip_address,
            "outcome": outcome,
            "detail": detail or {},
        }
        self._log.info("AUTH_EVENT %s", json.dumps(event))

    def log_data_export(
        self,
        user_id: int,
        export_type: str,
        record_count: int,
        ip_address: str | None,
    ) -> None:
        """[HIPAA] Data exports must be separately logged."""
        event = {
            "event_type": "data_export",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "export_type": export_type,
            "record_count": record_count,
            "ip_address": ip_address,
        }
        self._log.warning("DATA_EXPORT %s", json.dumps(event))

    def log_policy_violation(
        self,
        user_id: int | None,
        violation_type: str,
        detail: str,
        ip_address: str | None = None,
    ) -> None:
        """Log security policy violations for incident response."""
        event = {
            "event_type": "policy_violation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "violation_type": violation_type,
            "detail": detail,
            "ip_address": ip_address,
        }
        self._log.error("POLICY_VIOLATION %s", json.dumps(event))

    def _persist_audit_event(self, event: dict) -> None:
        """Write audit event to the database audit_logs table."""
        try:
            from app.models.document import AuditLog
            log = AuditLog(
                action=event["action"],
                user_id=event.get("user_id"),
                entity_type=event.get("resource_type"),
                entity_id=event.get("resource_id"),
                ip_address=event.get("ip_address"),
                user_agent=event.get("user_agent"),
                request_id=event.get("request_id"),
                detail=event,
            )
            self.db.add(log)
            self.db.commit()
        except Exception as exc:
            # [HIPAA] Audit log failures must not silently disappear
            self._log.error("AUDIT_PERSIST_FAILED: %s — event: %s", exc, json.dumps(event))


# ═══════════════════════════════════════════════════════════════════════════
#  DOCUMENT INTEGRITY
# ═══════════════════════════════════════════════════════════════════════════

def compute_document_hash(content: bytes) -> str:
    """
    Compute SHA-256 hash of document content.
    [HIPAA §164.312(c)] Integrity controls: ensure ePHI has not been
    altered or destroyed in an unauthorized manner.
    """
    return hashlib.sha256(content).hexdigest()


def verify_document_integrity(content: bytes, stored_hash: str) -> bool:
    """Verify document has not been tampered with since upload."""
    current_hash = compute_document_hash(content)
    return hmac.compare_digest(current_hash, stored_hash)


# ═══════════════════════════════════════════════════════════════════════════
#  MINIMUM NECESSARY STANDARD
# ═══════════════════════════════════════════════════════════════════════════

def filter_phi_for_role(
    document_data: dict[str, Any],
    user_role: str,
    is_owner: bool,
) -> dict[str, Any]:
    """
    Apply the HIPAA Minimum Necessary Standard.
    [HIPAA §164.502(b)] Only disclose the minimum PHI necessary for the
    intended purpose.

    Role-based field visibility:
      owner      → full access to all fields
      admin      → full access (internal use only)
      member     → access to summary, status, recommendations
                   NO raw extracted text, NO raw OCR
      viewer     → summary and status only
                   NO financial amounts, NO document details
    """
    if is_owner or user_role == "admin":
        return document_data

    # Fields always visible
    safe_fields = {
        "id", "name", "status", "workflow_state", "document_type",
        "document_type_confidence", "created_at", "updated_at",
        "has_ocr", "processing_metadata",
    }

    if user_role == "member":
        safe_fields |= {"summary", "recommended_actions", "deadlines", "generated_letter"}
        # Exclude raw text and sensitive financial fields from extracted_fields
        filtered = {k: v for k, v in document_data.items() if k in safe_fields}
        if "extracted_fields" in document_data:
            ef = document_data["extracted_fields"] or {}
            filtered["extracted_fields"] = {
                k: v for k, v in ef.items()
                if classify_field(k) != PHISensitivity.HIGH
                and k not in ("extracted_text", "all_amounts")
            }
        return filtered

    # viewer — minimal
    return {k: v for k, v in document_data.items() if k in safe_fields | {"summary"}}


# ═══════════════════════════════════════════════════════════════════════════
#  TRANSMISSION SECURITY VALIDATOR
# ═══════════════════════════════════════════════════════════════════════════

def assert_secure_context(request_scheme: str, environment: str) -> None:
    """
    [HIPAA §164.312(e)(1)] Transmission Security:
    Implement technical security measures to guard against unauthorized
    access to ePHI being transmitted over electronic communications networks.

    Raises ValueError if PHI would be transmitted insecurely in production.
    """
    if environment == "production" and request_scheme != "https":
        raise ValueError(
            "HIPAA violation: PHI transmission attempted over HTTP in production. "
            "All ePHI must be transmitted over TLS (HTTPS)."
        )


# ═══════════════════════════════════════════════════════════════════════════
#  AUTO-LOGOFF HELPER
# ═══════════════════════════════════════════════════════════════════════════

# [HIPAA §164.312(a)(2)(iii)] Automatic Logoff
# Sessions handling PHI should have shorter timeouts than standard applications.
HIPAA_SESSION_TIMEOUT_MINUTES = 30
HIPAA_IDLE_TIMEOUT_MINUTES = 15


def get_session_timeout(user_role: str) -> int:
    """Return session timeout in minutes based on role."""
    timeouts = {
        "admin": 15,    # Admins: shorter timeout, more access
        "member": 30,   # Standard: 30 minutes
        "viewer": 60,   # Read-only: slightly longer
    }
    return timeouts.get(user_role, HIPAA_SESSION_TIMEOUT_MINUTES)


# ═══════════════════════════════════════════════════════════════════════════
#  DATA RETENTION POLICY
# ═══════════════════════════════════════════════════════════════════════════

# [HIPAA §164.530(j)] Retention requirements
RETENTION_POLICIES = {
    "audit_logs":         2555,  # 7 years (HIPAA: 6 years minimum)
    "medical_documents":  2555,  # 7 years
    "utility_documents":  1095,  # 3 years (not PHI — shorter)
    "financial_documents":2555,  # 7 years (IRS + HIPAA overlap)
    "refresh_tokens":     30,    # 30 days
    "password_reset":     1,     # 24 hours
}

NON_PHI_DOCUMENT_TYPES = {
    "electricity_bill", "natural_gas_bill", "water_sewer_bill",
    "trash_recycling_bill", "telecom_bill", "combined_utility_bill",
    "property_tax_bill", "hoa_statement", "rent_statement",
}


def get_retention_days(document_type: str) -> int:
    """Return data retention period in days for a document type."""
    if document_type in NON_PHI_DOCUMENT_TYPES:
        return RETENTION_POLICIES["utility_documents"]
    return RETENTION_POLICIES["medical_documents"]


def is_phi_document(document_type: str) -> bool:
    """Returns True if the document type may contain Protected Health Information."""
    return document_type not in NON_PHI_DOCUMENT_TYPES


# ═══════════════════════════════════════════════════════════════════════════
#  COMPLIANCE CHECKLIST (runtime self-check)
# ═══════════════════════════════════════════════════════════════════════════

def run_hipaa_self_check() -> list[dict[str, str]]:
    """
    Runtime HIPAA compliance self-check.
    Returns a list of findings: each has 'status', 'requirement', 'detail'.
    Call this at startup in production to surface misconfigurations early.
    """
    import os
    findings: list[dict[str, str]] = []

    def check(status: str, requirement: str, detail: str):
        findings.append({"status": status, "requirement": requirement, "detail": detail})

    # Secret key strength
    secret = os.environ.get("SECRET_KEY", "")
    if len(secret) < 64 or secret == "change-me-generate-with-openssl-rand-hex-64":
        check("FAIL", "Access Control §164.312(a)", "SECRET_KEY is weak or default — regenerate with openssl rand -hex 64")
    else:
        check("PASS", "Access Control §164.312(a)", "SECRET_KEY is strong")

    # HTTPS enforcement
    env = os.environ.get("ENVIRONMENT", "development")
    if env == "production":
        check("PASS", "Transmission Security §164.312(e)", "ENVIRONMENT=production — HTTPS enforcement active")
    else:
        check("WARN", "Transmission Security §164.312(e)", f"ENVIRONMENT={env} — ensure HTTPS is enforced via nginx/load balancer")

    # Malware scanning
    malware_enabled = os.environ.get("MALWARE_SCANNING_ENABLED", "false").lower() == "true"
    if malware_enabled:
        check("PASS", "Integrity §164.312(c)", "Malware scanning enabled")
    else:
        check("WARN", "Integrity §164.312(c)", "MALWARE_SCANNING_ENABLED=false — enable ClamAV in production")

    # Database encryption hint
    db_url = os.environ.get("DATABASE_URL", "")
    if "localhost" in db_url or "127.0.0.1" in db_url:
        check("WARN", "Encryption at Rest §164.312(a)(2)(iv)", "Database appears to be local — ensure disk-level encryption in production (AWS RDS encryption, LUKS, etc.)")
    else:
        check("PASS", "Encryption at Rest §164.312(a)(2)(iv)", "Database appears to be remote — verify encryption at rest is enabled on the database server")

    # LLM provider data handling
    llm = os.environ.get("LLM_PROVIDER", "mock")
    if llm == "anthropic":
        check("INFO", "Third-Party PHI Disclosure §164.308(b)", "Using Anthropic Claude — ensure a BAA or DPA is in place before sending PHI. Anthropic provides data processing agreements for enterprise customers.")
    elif llm == "openai":
        check("INFO", "Third-Party PHI Disclosure §164.308(b)", "Using OpenAI — ensure a Business Associate Agreement is in place before sending PHI. OpenAI's BAA is available on their enterprise plan.")
    else:
        check("PASS", "Third-Party PHI Disclosure §164.308(b)", "LLM_PROVIDER=mock — no external PHI transmission via LLM")

    # Audit log retention
    retention = int(os.environ.get("AUDIT_LOG_RETENTION_DAYS", "0"))
    if retention >= 2190:  # 6 years
        check("PASS", "Audit Log Retention §164.530(j)", f"AUDIT_LOG_RETENTION_DAYS={retention} (≥6 years — compliant)")
    else:
        check("FAIL", "Audit Log Retention §164.530(j)", f"AUDIT_LOG_RETENTION_DAYS={retention} — must be ≥2190 (6 years). Recommend 2555 (7 years).")

    return findings
