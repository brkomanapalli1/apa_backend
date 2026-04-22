"""
Run this once to add all missing document type values to the
document_type_enum in PostgreSQL.

Usage:
    cd backend
    .venv\\Scripts\\activate
    python fix_document_type_enum.py
"""
from app.db.session import SessionLocal
from sqlalchemy import text

NEW_TYPES = [
    "social_security_notice",
    "prescription_drug_notice",
    "veterans_benefits_letter",
    "electricity_bill",
    "natural_gas_bill",
    "water_sewer_bill",
    "trash_recycling_bill",
    "telecom_bill",
    "combined_utility_bill",
    "rent_statement",
    "hoa_statement",
    "property_tax_bill",
    "mortgage_statement",
    "home_insurance_bill",
    "credit_card_statement",
    "bank_statement",
    "loan_statement",
    "collection_notice",
    "irs_notice",
    "food_assistance_notice",
    "housing_assistance_notice",
    "financial_assistance_letter",
]

db = SessionLocal()
for t in NEW_TYPES:
    stmt = f"ALTER TYPE document_type_enum ADD VALUE IF NOT EXISTS '{t}'"
    try:
        db.execute(text(stmt))
        db.commit()
        print(f"OK: {t}")
    except Exception as e:
        db.rollback()
        print(f"SKIP ({t}): {e}")

db.close()
print("\nAll done — restart uvicorn then re-upload your document.")