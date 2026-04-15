from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class SubscriptionStatus(StrEnum):
    FREE = "free"
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class DocumentStatus(StrEnum):
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    PROCESSED = "processed"
    COMPLETED = "completed"
    FAILED = "failed"
    QUARANTINED = "quarantined"


class DocumentType(StrEnum):
    MEDICARE_SUMMARY_NOTICE = "medicare_summary_notice"
    EXPLANATION_OF_BENEFITS = "explanation_of_benefits"
    CLAIM_DENIAL_LETTER = "claim_denial_letter"
    ITEMIZED_MEDICAL_BILL = "itemized_medical_bill"
    MEDICAID_NOTICE = "medicaid_notice"
    UNKNOWN = "unknown"


class MalwareScanStatus(StrEnum):
    PENDING = "pending"
    CLEAN = "clean"
    INFECTED = "infected"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowState(StrEnum):
    NEW = "new"
    NEEDS_REVIEW = "needs_review"
    IN_PROGRESS = "in_progress"
    WAITING_ON_USER = "waiting_on_user"
    DONE = "done"


class SharePermission(StrEnum):
    VIEWER = "viewer"
    REVIEWER = "reviewer"
    EDITOR = "editor"


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"
    PUSH = "push"
    SMS = "sms"


class ReminderStatus(StrEnum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    DISMISSED = "dismissed"
    FAILED = "failed"


class SSOProvider(StrEnum):
    GOOGLE = "google"
