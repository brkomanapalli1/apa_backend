"""0009 — Fix all enum values + add all 27 document types

This migration consolidates ALL the manual database fixes that were
applied locally into a single tracked migration. Running this on any
environment (dev, qa, prod) brings the database to the correct state.

Fixes applied:
  1. document_status_enum   — add: quarantined, uploading
  2. malware_scan_status_enum — add: skipped
  3. workflow_state_enum    — add: needs_review, waiting_on_user, resolved
  4. document_type_enum     — add all 22 missing document types:
       social_security_notice, prescription_drug_notice,
       veterans_benefits_letter, electricity_bill, natural_gas_bill,
       water_sewer_bill, trash_recycling_bill, telecom_bill,
       combined_utility_bill, rent_statement, hoa_statement,
       property_tax_bill, mortgage_statement, home_insurance_bill,
       credit_card_statement, bank_statement, loan_statement,
       collection_notice, irs_notice, food_assistance_notice,
       housing_assistance_notice, financial_assistance_letter

NOTE: PostgreSQL requires each ALTER TYPE ... ADD VALUE to be committed
separately (cannot be in a transaction block). We use
execute_if(dialect='postgresql') and individual commits.

Revision: 0009
Revises:  0008
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


# All enum additions needed — (enum_name, value)
_ENUM_ADDITIONS = [
    # document_status_enum
    ("document_status_enum", "quarantined"),
    ("document_status_enum", "uploading"),

    # malware_scan_status_enum
    ("malware_scan_status_enum", "skipped"),

    # workflow_state_enum
    ("workflow_state_enum", "needs_review"),
    ("workflow_state_enum", "waiting_on_user"),
    ("workflow_state_enum", "resolved"),

    # document_type_enum — all 22 missing types
    ("document_type_enum", "social_security_notice"),
    ("document_type_enum", "prescription_drug_notice"),
    ("document_type_enum", "veterans_benefits_letter"),
    ("document_type_enum", "electricity_bill"),
    ("document_type_enum", "natural_gas_bill"),
    ("document_type_enum", "water_sewer_bill"),
    ("document_type_enum", "trash_recycling_bill"),
    ("document_type_enum", "telecom_bill"),
    ("document_type_enum", "combined_utility_bill"),
    ("document_type_enum", "rent_statement"),
    ("document_type_enum", "hoa_statement"),
    ("document_type_enum", "property_tax_bill"),
    ("document_type_enum", "mortgage_statement"),
    ("document_type_enum", "home_insurance_bill"),
    ("document_type_enum", "credit_card_statement"),
    ("document_type_enum", "bank_statement"),
    ("document_type_enum", "loan_statement"),
    ("document_type_enum", "collection_notice"),
    ("document_type_enum", "irs_notice"),
    ("document_type_enum", "food_assistance_notice"),
    ("document_type_enum", "housing_assistance_notice"),
    ("document_type_enum", "financial_assistance_letter"),
]


def upgrade() -> None:
    # PostgreSQL requires ALTER TYPE ADD VALUE outside a transaction.
    # We use op.execute with COMMIT between each statement.
    conn = op.get_bind()

    for enum_name, value in _ENUM_ADDITIONS:
        # IF NOT EXISTS means this is safe to run multiple times —
        # already-present values are silently skipped.
        conn.execute(sa.text(
            f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}'"
        ))
        # Each ADD VALUE must be committed before the next one
        conn.execute(sa.text("COMMIT"))

    # Re-open transaction for Alembic to close cleanly
    conn.execute(sa.text("BEGIN"))


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # Downgrade is a no-op — values stay but are unused.
    pass
