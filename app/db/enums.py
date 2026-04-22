from enum import StrEnum


class UserRole(StrEnum):
    ADMIN  = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class SubscriptionStatus(StrEnum):
    FREE      = "free"
    TRIAL     = "trial"
    ACTIVE    = "active"
    PAST_DUE  = "past_due"
    CANCELED  = "canceled"


class DocumentStatus(StrEnum):
    UPLOADING    = "uploading"
    UPLOADED     = "uploaded"
    QUEUED       = "queued"
    PROCESSING   = "processing"
    PROCESSED    = "processed"
    COMPLETED    = "completed"
    FAILED       = "failed"
    QUARANTINED  = "quarantined"


class DocumentType(StrEnum):
    # ── Medical ──────────────────────────────────────────────────────────
    MEDICARE_SUMMARY_NOTICE   = "medicare_summary_notice"
    EXPLANATION_OF_BENEFITS   = "explanation_of_benefits"
    CLAIM_DENIAL_LETTER       = "claim_denial_letter"
    ITEMIZED_MEDICAL_BILL     = "itemized_medical_bill"
    MEDICAID_NOTICE           = "medicaid_notice"
    SOCIAL_SECURITY_NOTICE    = "social_security_notice"
    PRESCRIPTION_DRUG_NOTICE  = "prescription_drug_notice"
    VETERANS_BENEFITS_LETTER  = "veterans_benefits_letter"

    # ── Utility ───────────────────────────────────────────────────────────
    ELECTRICITY_BILL          = "electricity_bill"
    NATURAL_GAS_BILL          = "natural_gas_bill"
    WATER_SEWER_BILL          = "water_sewer_bill"
    TRASH_RECYCLING_BILL      = "trash_recycling_bill"
    TELECOM_BILL              = "telecom_bill"
    COMBINED_UTILITY_BILL     = "combined_utility_bill"

    # ── Housing & Property ────────────────────────────────────────────────
    RENT_STATEMENT            = "rent_statement"
    HOA_STATEMENT             = "hoa_statement"
    PROPERTY_TAX_BILL         = "property_tax_bill"
    MORTGAGE_STATEMENT        = "mortgage_statement"
    HOME_INSURANCE_BILL       = "home_insurance_bill"

    # ── Financial ─────────────────────────────────────────────────────────
    CREDIT_CARD_STATEMENT     = "credit_card_statement"
    BANK_STATEMENT            = "bank_statement"
    LOAN_STATEMENT            = "loan_statement"
    COLLECTION_NOTICE         = "collection_notice"
    IRS_NOTICE                = "irs_notice"
    FOOD_ASSISTANCE_NOTICE    = "food_assistance_notice"
    HOUSING_ASSISTANCE_NOTICE = "housing_assistance_notice"
    FINANCIAL_ASSISTANCE_LETTER = "financial_assistance_letter"

    # ── Fallback ──────────────────────────────────────────────────────────
    UNKNOWN                   = "unknown"


class MalwareScanStatus(StrEnum):
    PENDING   = "pending"
    CLEAN     = "clean"
    INFECTED  = "infected"
    FAILED    = "failed"
    SKIPPED   = "skipped"


class WorkflowState(StrEnum):
    NEW            = "new"
    NEEDS_REVIEW   = "needs_review"
    IN_PROGRESS    = "in_progress"
    WAITING_ON_USER = "waiting_on_user"
    RESOLVED       = "resolved"
    DONE           = "done"


class SharePermission(StrEnum):
    VIEWER   = "viewer"
    REVIEWER = "reviewer"
    EDITOR   = "editor"


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    EMAIL  = "email"
    PUSH   = "push"
    SMS    = "sms"


class ReminderStatus(StrEnum):
    SCHEDULED = "scheduled"
    SENT      = "sent"
    DISMISSED = "dismissed"
    FAILED    = "failed"


class SSOProvider(StrEnum):
    GOOGLE = "google"