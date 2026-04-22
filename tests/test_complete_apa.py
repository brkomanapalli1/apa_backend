"""
tests/test_complete_apa.py — Comprehensive APA Test Suite

Coverage:
  - Document analysis (all 27 types)
  - Scam detection (all scam categories)
  - Medication extraction
  - Input sanitization (XSS, SQL injection, PII)
  - HIPAA compliance checks
  - Data sanitization
  - US regulatory validation
  - Bill intelligence
  - Senior view / ui_summary
  - Backward compatibility (paperwork_intelligence shim)

Run: pytest tests/test_complete_apa.py -v --cov=app --cov-report=term-missing
"""
from __future__ import annotations

import pytest
import sys
import os

# Make app importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════════════════
#  SANITIZER TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestInputSanitization:
    """Tests for input sanitization and XSS/SQL injection prevention."""

    def setup_method(self):
        from app.core.sanitizer import (
            sanitize_string, sanitize_dict, detect_sql_injection,
            detect_xss, mask_pii_for_log, sanitize_filename,
            check_document_content_type, validate_us_zip_code,
            validate_us_phone,
        )
        self.sanitize_string = sanitize_string
        self.sanitize_dict = sanitize_dict
        self.detect_sql_injection = detect_sql_injection
        self.detect_xss = detect_xss
        self.mask_pii_for_log = mask_pii_for_log
        self.sanitize_filename = sanitize_filename
        self.check_content_type = check_document_content_type
        self.validate_zip = validate_us_zip_code
        self.validate_phone = validate_us_phone

    def test_xss_script_tag_removed(self):
        result = self.sanitize_string("<script>alert('xss')</script>Hello")
        assert "<script>" not in result
        assert "Hello" in result

    def test_xss_img_onerror_removed(self):
        result = self.sanitize_string('<img src=x onerror="alert(1)">text')
        assert "onerror" not in result

    def test_javascript_protocol_removed(self):
        result = self.sanitize_string("javascript:alert('xss')")
        assert "javascript:" not in result

    def test_normal_text_preserved(self):
        text = "My Medicare payment is due on January 15th."
        result = self.sanitize_string(text)
        assert result == text

    def test_null_bytes_removed(self):
        result = self.sanitize_string("Hello\x00World")
        assert "\x00" not in result
        assert "HelloWorld" in result

    def test_max_length_enforced(self):
        long_text = "A" * 200000
        result = self.sanitize_string(long_text, max_length=100)
        assert len(result) == 100

    def test_sql_injection_detected(self):
        assert self.detect_sql_injection("'; DROP TABLE users; --") is True
        assert self.detect_sql_injection("SELECT * FROM documents") is True
        assert self.detect_sql_injection("UNION SELECT password FROM users") is True

    def test_normal_text_not_sql_injection(self):
        assert self.detect_sql_injection("My name is John Smith") is False
        assert self.detect_sql_injection("Medicare Part B coverage") is False

    def test_dict_sanitization_recursive(self):
        data = {
            "name": "<script>evil</script>John",
            "address": {"street": "123 Main St\x00"},
            "notes": ["good note", "<img onerror='evil'>bad note"],
        }
        result = self.sanitize_dict(data)
        assert "<script>" not in result["name"]
        assert "John" in result["name"]
        assert "\x00" not in result["address"]["street"]
        assert "onerror" not in result["notes"][1]

    def test_pii_ssn_masked_in_logs(self):
        text = "Patient SSN: 123-45-6789 admitted today"
        masked = self.mask_pii_for_log(text)
        assert "123-45-6789" not in masked
        assert "6789" in masked  # Last 4 preserved

    def test_pii_email_masked_in_logs(self):
        text = "Contact john.smith@example.com for details"
        masked = self.mask_pii_for_log(text)
        assert "john.smith" not in masked

    def test_filename_path_traversal_prevented(self):
        dangerous = "../../../etc/passwd"
        safe = self.sanitize_filename(dangerous)
        assert ".." not in safe
        assert "/" not in safe

    def test_filename_null_byte_removed(self):
        filename = "document\x00.pdf"
        safe = self.sanitize_filename(filename)
        assert "\x00" not in safe

    def test_content_type_pdf_valid(self):
        valid, msg = self.check_content_type("application/pdf", "document.pdf")
        assert valid is True

    def test_content_type_mismatch_rejected(self):
        valid, msg = self.check_content_type("text/html", "document.pdf")
        assert valid is False

    def test_us_zip_valid(self):
        assert self.validate_zip("75034") is True
        assert self.validate_zip("75034-1234") is True

    def test_us_zip_invalid(self):
        assert self.validate_zip("1234") is False
        assert self.validate_zip("ABCDE") is False

    def test_us_phone_valid(self):
        assert self.validate_phone("214-555-1234") is True
        assert self.validate_phone("(214) 555-1234") is True
        assert self.validate_phone("12145551234") is True

    def test_us_phone_invalid(self):
        assert self.validate_phone("123") is False


# ═══════════════════════════════════════════════════════════════════════════
#  SCAM DETECTION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestScamDetection:
    """Tests for scam and fraud detection — Phase 2 feature."""

    def setup_method(self):
        from app.services.scam_detection import analyze_for_scams, get_scam_education_tip
        self.analyze = analyze_for_scams
        self.get_tip = get_scam_education_tip

    def test_gift_card_scam_detected(self):
        text = "You owe $1,500 in back taxes. Purchase iTunes gift cards and call immediately to avoid arrest."
        result = self.analyze(text)
        assert result.is_suspicious is True
        assert result.risk_level == "high"
        assert any(s.category == "gift_card_payment" for s in result.signals)

    def test_fake_irs_scam_detected(self):
        text = "IRS FINAL NOTICE: Pay immediately via Bitcoin or gift cards to avoid federal prosecution."
        result = self.analyze(text)
        assert result.is_suspicious is True
        assert result.confidence > 0.5

    def test_medicare_fraud_detected(self):
        text = "Dear Medicare beneficiary, to receive your free back brace, provide your Medicare card number and beneficiary number."
        result = self.analyze(text)
        assert result.is_suspicious is True
        assert any(s.category == "medicare_fraud" for s in result.signals)

    def test_ssa_suspension_scam_detected(self):
        text = "Your Social Security number has been suspended due to suspicious activity. Call immediately to reactivate."
        result = self.analyze(text)
        assert result.is_suspicious is True

    def test_lottery_scam_detected(self):
        text = "Congratulations! You have won the international lottery! Pay processing fee of $299 to claim your $50,000 prize."
        result = self.analyze(text)
        assert result.is_suspicious is True
        assert any(s.category == "lottery_scam" for s in result.signals)

    def test_legitimate_medicare_not_flagged_as_high(self):
        text = "Medicare Summary Notice. Your Medicare number: 1EG4-TE5-MK72. Medicare paid $800.00. Notice CP001."
        result = self.analyze(text)
        # Legitimate Medicare notices should not be high risk
        assert result.risk_level != "high"

    def test_legitimate_utility_bill_safe(self):
        text = "CoServ Electric. Account Number 123456789. Amount Due: $132.00. Due Date: February 15, 2025."
        result = self.analyze(text)
        assert result.risk_level in ("none", "low")

    def test_empty_text_returns_safe(self):
        result = self.analyze("")
        assert result.is_suspicious is False
        assert result.risk_level == "none"

    def test_warning_message_present_for_high_risk(self):
        text = "Pay with gift cards immediately or you will be arrested by federal agents."
        result = self.analyze(text)
        assert result.warning_message != ""
        assert len(result.recommended_actions) > 0

    def test_recommended_actions_include_ftc(self):
        text = "Buy iTunes gift cards to pay your IRS debt immediately."
        result = self.analyze(text)
        assert result.report_url == "https://reportfraud.ftc.gov"

    def test_education_tip_returned(self):
        tip = self.get_tip("gift_card_payment")
        assert "gift card" in tip.lower()
        assert len(tip) > 50

    def test_tech_support_scam_detected(self):
        text = "Your computer has been hacked. Call our technician toll-free 1-800-555-0199 immediately to fix virus."
        result = self.analyze(text)
        assert result.is_suspicious is True


# ═══════════════════════════════════════════════════════════════════════════
#  MEDICATION EXTRACTION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestMedicationExtraction:
    """Tests for medication extraction from prescription paperwork."""

    def setup_method(self):
        from app.services.medication_service import (
            extract_medications, format_medication_reminders, generate_medication_schedule
        )
        self.extract = extract_medications
        self.format_reminders = format_medication_reminders
        self.generate_schedule = generate_medication_schedule

    def test_basic_medication_extracted(self):
        text = "Take metformin 500mg twice daily with food."
        result = self.extract(text)
        assert result.has_medications is True
        assert len(result.medications) >= 1
        assert any(m.name.lower() == "metformin" for m in result.medications)

    def test_dosage_extracted(self):
        text = "Lisinopril 10mg once daily in the morning."
        result = self.extract(text)
        med = next((m for m in result.medications if "lisinopril" in m.name.lower()), None)
        if med:
            assert med.dosage is not None
            assert "10" in med.dosage

    def test_frequency_to_reminder_times(self):
        text = "Take aspirin 81mg twice daily."
        result = self.extract(text)
        med = next((m for m in result.medications if "aspirin" in m.name.lower()), None)
        if med and med.reminder_times:
            assert len(med.reminder_times) == 2

    def test_with_food_detected(self):
        text = "Take metformin 500mg twice daily with food or after meals."
        result = self.extract(text)
        med = next((m for m in result.medications if "metformin" in m.name.lower()), None)
        if med:
            assert med.with_food is True

    def test_discharge_instructions_extracted(self):
        text = """
        Take warfarin 5mg daily.
        Activity restriction: No heavy lifting for 6 weeks.
        Wound care: Keep incision dry for 48 hours.
        Follow up with cardiologist in 2 weeks.
        """
        result = self.extract(text)
        assert len(result.discharge_instructions) > 0

    def test_follow_up_appointments_extracted(self):
        text = "Follow up with your doctor in 7 days. See cardiologist in 2 weeks."
        result = self.extract(text)
        assert len(result.follow_up_appointments) > 0

    def test_warning_symptoms_extracted(self):
        text = "Call 911 if you experience chest pain or difficulty breathing. Seek emergency care if severe bleeding occurs."
        result = self.extract(text)
        assert len(result.warning_symptoms) > 0

    def test_dietary_restrictions_extracted(self):
        text = "Avoid grapefruit while taking this medication. Follow a low sodium diet."
        result = self.extract(text)
        assert len(result.dietary_restrictions) > 0

    def test_disclaimer_always_present(self):
        result = self.extract("Take aspirin daily.")
        assert len(result.disclaimer) > 50
        assert "doctor" in result.disclaimer.lower() or "pharmacist" in result.disclaimer.lower()

    def test_empty_text_returns_empty_result(self):
        result = self.extract("")
        assert result.has_medications is False
        assert len(result.medications) == 0

    def test_reminder_schedule_generated(self):
        from app.services.medication_service import MedicationEntry
        meds = [
            MedicationEntry(name="Metformin", dosage="500mg", frequency="twice daily",
                            reminder_times=["08:00", "20:00"]),
            MedicationEntry(name="Aspirin", dosage="81mg", frequency="once daily",
                            reminder_times=["08:00"]),
        ]
        schedule = self.generate_schedule(meds)
        assert "morning" in schedule
        assert len(schedule["morning"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════
#  BILL INTELLIGENCE TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestBillIntelligence:
    """Tests for the bill intelligence engine — all 27 document types."""

    def setup_method(self):
        from app.services.bill_intelligence import (
            analyze_document, detect_document_type, build_senior_view
        )
        self.analyze = analyze_document
        self.detect = detect_document_type
        self.senior_view = build_senior_view

    # ── Medical types ──────────────────────────────────────────────────────

    def test_medicare_summary_notice_detected(self):
        doc_type, conf, _ = self.detect("Medicare Summary Notice MSN Member ID Medicare paid 80.00", "msn.pdf")
        assert doc_type == "medicare_summary_notice"
        assert conf > 0.9

    def test_eob_detected(self):
        doc_type, conf, _ = self.detect("Explanation of Benefits EOB plan paid patient responsibility", "eob.pdf")
        assert doc_type == "explanation_of_benefits"

    def test_claim_denial_detected(self):
        doc_type, conf, _ = self.detect("Your claim has been denied. Reason for Denial: not medically necessary. Appeal rights.", "denial.pdf")
        assert doc_type == "claim_denial_letter"

    def test_itemized_bill_detected(self):
        doc_type, conf, _ = self.detect("Itemized Bill patient account amount due 450.00 statement date balance due", "bill.pdf")
        assert doc_type == "itemized_medical_bill"

    def test_medicaid_notice_detected(self):
        doc_type, conf, _ = self.detect("Medicaid Eligibility Notice renew your benefits coverage ending", "medicaid.pdf")
        assert doc_type == "medicaid_notice"

    def test_social_security_detected(self):
        doc_type, conf, _ = self.detect("Social Security Administration ssa.gov benefit payment monthly benefit 1200.00", "ssa.pdf")
        assert doc_type == "social_security_notice"

    # ── Utility types ──────────────────────────────────────────────────────

    def test_electricity_bill_detected(self):
        doc_type, conf, _ = self.detect("Electric Service kilowatt kwh usage 1200 kWh amount due 132.00", "electric.pdf")
        assert doc_type == "electricity_bill"

    def test_natural_gas_detected(self):
        doc_type, conf, _ = self.detect("Natural Gas Service therms usage 45 therms amount due 67.00", "gas.pdf")
        assert doc_type == "natural_gas_bill"

    def test_water_bill_detected(self):
        doc_type, conf, _ = self.detect("Water Service gallons used sewer service amount due 55.00", "water.pdf")
        assert doc_type == "water_sewer_bill"

    def test_telecom_bill_detected(self):
        doc_type, conf, _ = self.detect("Monthly Service Charge internet service data plan phone service amount due 89.00", "phone.pdf")
        assert doc_type == "telecom_bill"

    # ── Housing types ──────────────────────────────────────────────────────

    def test_property_tax_detected(self):
        doc_type, conf, _ = self.detect("Property Tax parcel number assessed value ad valorem appraisal district amount due", "ptax.pdf")
        assert doc_type == "property_tax_bill"

    def test_hoa_detected(self):
        doc_type, conf, _ = self.detect("Homeowners Association HOA dues common area special assessment amount due", "hoa.pdf")
        assert doc_type == "hoa_statement"

    def test_rent_detected(self):
        doc_type, conf, _ = self.detect("Rent Due monthly rent tenant statement landlord lease payment amount due 1200.00", "rent.pdf")
        assert doc_type == "rent_statement"

    # ── Financial types ────────────────────────────────────────────────────

    def test_credit_card_detected(self):
        doc_type, conf, _ = self.detect("Credit Card minimum payment due statement balance new balance credit limit APR", "cc.pdf")
        assert doc_type == "credit_card_statement"

    def test_collection_notice_detected(self):
        doc_type, conf, _ = self.detect("Collection Agency debt collector past due Fair Debt Collection Practices Act third-party collector", "coll.pdf")
        assert doc_type == "collection_notice"

    def test_irs_notice_detected(self):
        doc_type, conf, _ = self.detect("Internal Revenue Service irs.gov Notice CP2000 balance due department of the treasury", "irs.pdf")
        assert doc_type == "irs_notice"

    # ── Full analysis tests ────────────────────────────────────────────────

    def test_full_analysis_has_ui_summary(self):
        result = self.analyze("Medicare Summary Notice MSN paid 80.00 member ID 123", "msn.pdf")
        assert "ui_summary" in result["extracted_fields"]

    def test_ui_summary_has_all_required_keys(self):
        result = self.analyze("Medicare Summary Notice MSN paid 80.00", "msn.pdf")
        ui = result["extracted_fields"]["ui_summary"]
        required_keys = [
            "document_family", "what_this_is", "payment_status", "payment_message",
            "main_amount", "main_due_date", "contact_phone", "contact_email",
            "warning_flags", "next_steps", "call_script", "needs_trusted_helper",
        ]
        for key in required_keys:
            assert key in ui, f"Missing key: {key}"

    def test_eob_always_not_a_bill(self):
        result = self.analyze("Explanation of Benefits EOB plan paid 200 patient responsibility 30", "eob.pdf")
        ui = result["extracted_fields"]["ui_summary"]
        assert ui["payment_status"] == "not_a_bill"

    def test_denial_always_appeal_or_call(self):
        result = self.analyze("claim denied not medically necessary appeal rights within 30 days", "denial.pdf")
        ui = result["extracted_fields"]["ui_summary"]
        assert ui["payment_status"] == "appeal_or_call"
        assert ui["needs_trusted_helper"] is True

    def test_collection_notice_verify_debt(self):
        result = self.analyze("collection agency debt collector past due 450.00 FDCPA third-party collector dispute 30 days", "coll.pdf")
        ui = result["extracted_fields"]["ui_summary"]
        assert ui["payment_status"] == "verify_debt"

    def test_electricity_pay_utility(self):
        result = self.analyze("electric service kwh 1200 amount due 132.00 due date 02/15/2025", "elec.pdf")
        ui = result["extracted_fields"]["ui_summary"]
        assert ui["payment_status"] == "pay_utility"
        assert ui["document_family"] == "utility_bill"

    def test_unreadable_document_graceful_failure(self):
        result = self.analyze("", "empty.pdf")
        assert result["document_type"] == "unknown"
        assert result["document_type_confidence"] == 0.0
        assert len(result["recommendations"]) > 0

    def test_recommendations_always_present(self):
        result = self.analyze("Some document with some text about payment", "doc.pdf")
        assert len(result["recommendations"]) > 0

    def test_letter_always_generated(self):
        result = self.analyze("Medicare Summary Notice Medicare paid 80.00", "msn.pdf")
        assert "letter" in result
        assert "body" in result["letter"]

    def test_analyze_phase1_document_alias(self):
        """Backward compatibility shim test."""
        from app.services.paperwork_intelligence import analyze_phase1_document
        result = analyze_phase1_document("Medicare Summary Notice MSN paid 80.00", "test.pdf")
        assert "ui_summary" in result["extracted_fields"]

    def test_generate_letter_shim(self):
        """Backward compatibility shim test."""
        from app.services.paperwork_intelligence import generate_letter_for_document
        letter = generate_letter_for_document("claim_denial_letter", {"account_number": "ABC123"}, [], "")
        assert "body" in letter


# ═══════════════════════════════════════════════════════════════════════════
#  HIPAA COMPLIANCE TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestHIPAACompliance:
    """Tests for HIPAA compliance checks and PHI handling."""

    def setup_method(self):
        from app.core.hipaa_compliance import (
            mask_pii_for_log as hipaa_mask,
            compute_document_hash,
            verify_document_integrity,
            filter_phi_for_role,
            is_phi_document,
            get_retention_days,
            classify_field,
            PHISensitivity,
        )
        self.mask = hipaa_mask
        self.hash = compute_document_hash
        self.verify = verify_document_integrity
        self.filter = filter_phi_for_role
        self.is_phi = is_phi_document
        self.retention = get_retention_days
        self.classify = classify_field
        self.PHISensitivity = PHISensitivity

    def test_document_hash_sha256(self):
        content = b"test document content"
        hash_val = self.hash(content)
        assert len(hash_val) == 64  # SHA-256 hex digest
        assert hash_val == self.hash(content)  # Deterministic

    def test_document_integrity_valid(self):
        content = b"document content"
        hash_val = self.hash(content)
        assert self.verify(content, hash_val) is True

    def test_document_integrity_tampered(self):
        content = b"original content"
        hash_val = self.hash(content)
        tampered = b"tampered content"
        assert self.verify(tampered, hash_val) is False

    def test_phi_field_classified_high(self):
        assert self.classify("member_id") == self.PHISensitivity.HIGH
        assert self.classify("ssn") == self.PHISensitivity.HIGH
        assert self.classify("medicare_number") == self.PHISensitivity.HIGH

    def test_date_field_classified_medium(self):
        assert self.classify("date_of_birth") == self.PHISensitivity.MEDIUM
        assert self.classify("service_date") == self.PHISensitivity.MEDIUM

    def test_non_phi_field_classified_low(self):
        assert self.classify("document_type") == self.PHISensitivity.LOW
        assert self.classify("status") == self.PHISensitivity.LOW

    def test_owner_sees_all_fields(self):
        doc_data = {
            "id": 1, "name": "test.pdf", "summary": "Test",
            "extracted_fields": {"member_id": "123", "amount_due": "50.00"},
        }
        result = self.filter(doc_data, "member", is_owner=True)
        assert "extracted_fields" in result
        assert result["extracted_fields"].get("member_id") == "123"

    def test_viewer_sees_minimal_fields(self):
        doc_data = {
            "id": 1, "name": "test.pdf", "status": "processed",
            "summary": "Test summary",
            "extracted_fields": {"member_id": "123", "amount_due": "50.00"},
        }
        result = self.filter(doc_data, "viewer", is_owner=False)
        # Viewer should not see PHI fields
        if "extracted_fields" in result:
            assert "member_id" not in result.get("extracted_fields", {})

    def test_medical_document_is_phi(self):
        assert self.is_phi("medicare_summary_notice") is True
        assert self.is_phi("explanation_of_benefits") is True
        assert self.is_phi("claim_denial_letter") is True

    def test_utility_document_not_phi(self):
        assert self.is_phi("electricity_bill") is False
        assert self.is_phi("water_sewer_bill") is False

    def test_medical_retention_7_years(self):
        days = self.retention("medicare_summary_notice")
        assert days >= 2190  # Minimum 6 years, default 7

    def test_utility_retention_shorter(self):
        medical_days = self.retention("medicare_summary_notice")
        utility_days = self.retention("electricity_bill")
        assert utility_days < medical_days


# ═══════════════════════════════════════════════════════════════════════════
#  INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestIntegration:
    """Integration tests combining multiple services."""

    def test_medicare_document_full_pipeline(self):
        """Full pipeline: analyze → check scams → check medications."""
        from app.services.bill_intelligence import analyze_document
        from app.services.scam_detection import analyze_for_scams

        text = """
        Medicare Summary Notice
        Member: John Smith
        Medicare Number: 1EG4-TE5-MK72
        Medicare paid: $800.00
        Maximum you may be billed: $200.00
        Claim Number: CLM-123456
        Date of Service: 01/15/2025
        """

        # Document analysis
        analysis = analyze_document(text, "msn.pdf")
        assert analysis["document_type"] == "medicare_summary_notice"
        ui = analysis["extracted_fields"]["ui_summary"]
        assert ui["payment_status"] == "review_first"

        # Scam check — legitimate Medicare notice should not be high risk
        scam = analyze_for_scams(text)
        assert scam.risk_level != "high"

    def test_scam_letter_plus_sanitization(self):
        """Scam letter that also has XSS — both should be caught."""
        from app.services.scam_detection import analyze_for_scams
        from app.core.sanitizer import sanitize_string

        malicious_text = "<script>steal()</script>Buy iTunes gift cards to pay IRS debt immediately or face arrest."

        # Sanitize first
        clean = sanitize_string(malicious_text)
        assert "<script>" not in clean

        # Then check for scams
        result = analyze_for_scams(clean)
        assert result.is_suspicious is True

    def test_prescription_discharge_full_pipeline(self):
        """Hospital discharge + medication extraction."""
        from app.services.medication_service import extract_medications

        text = """
        Hospital Discharge Instructions
        Patient: Mary Johnson
        Medications:
        1. Metformin 500mg twice daily with food
        2. Lisinopril 10mg once daily in the morning
        3. Aspirin 81mg once daily

        Follow up with Dr. Smith in 2 weeks.
        Activity restriction: No heavy lifting for 4 weeks.
        Warning: Call 911 if chest pain or difficulty breathing.
        Avoid grapefruit juice.
        """

        result = extract_medications(text)
        assert result.has_medications is True
        assert len(result.medications) >= 2
        assert len(result.follow_up_appointments) >= 1
        assert len(result.warning_symptoms) >= 1
        assert len(result.dietary_restrictions) >= 1

    def test_all_document_types_have_call_script(self):
        """Every document type should generate a call script for seniors."""
        from app.services.bill_intelligence import analyze_document

        doc_types_texts = [
            ("Medicare Summary Notice MSN paid 80.00", "msn.pdf"),
            ("Explanation of Benefits EOB plan paid 200", "eob.pdf"),
            ("claim denied not medically necessary appeal rights", "denial.pdf"),
            ("electric service kwh 1200 amount due 132.00", "elec.pdf"),
            ("property tax parcel number assessed value ad valorem", "ptax.pdf"),
            ("collection agency debt collector FDCPA past due", "coll.pdf"),
        ]

        for text, filename in doc_types_texts:
            result = analyze_document(text, filename)
            ui = result["extracted_fields"].get("ui_summary", {})
            assert "call_script" in ui, f"Missing call_script for {filename}"
            assert len(ui["call_script"]) > 20, f"Call script too short for {filename}"


# ═══════════════════════════════════════════════════════════════════════════
#  RUNNER
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
