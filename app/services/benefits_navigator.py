"""
benefits_navigator.py — Government Benefits Navigator (Phase 4)

Helps seniors discover and understand benefits they may qualify for:
  - Medicaid
  - Medicare Savings Programs (MSP)
  - Extra Help / Low Income Subsidy (LIS)
  - Supplemental Security Income (SSI)
  - SNAP (food assistance)
  - LIHEAP (energy assistance)
  - Veterans benefits (VA)
  - Property tax relief programs
  - State Pharmaceutical Assistance Programs (SPAPs)
  - Medicare Advantage Special Enrollment

Based on US federal and state programs as of 2025.
Always includes disclaimer to verify with official agency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BenefitProgram:
    name: str
    agency: str
    description: str
    eligibility_summary: str
    income_limit_note: str
    how_to_apply: str
    phone: str
    website: str
    category: str
    potentially_eligible: bool = False
    priority: str = "medium"  # "high" | "medium" | "low"
    apply_url: str = ""


# ── US Federal Benefit Programs ───────────────────────────────────────────

ALL_PROGRAMS: list[BenefitProgram] = [
    BenefitProgram(
        name="Medicare Savings Programs (MSP)",
        agency="Centers for Medicare & Medicaid Services",
        description="Helps pay Medicare premiums, deductibles, and co-payments.",
        eligibility_summary="Must have Medicare Part A and B. Income and resource limits apply (vary by state).",
        income_limit_note="Roughly $1,200–$1,600/month for individuals (2024). Check with your state.",
        how_to_apply="Contact your State Medicaid office or call 1-800-MEDICARE.",
        phone="1-800-633-4227",
        website="https://www.medicare.gov/basics/costs/help/medicare-savings-programs",
        category="medicare",
        apply_url="https://www.benefits.gov/benefit/1551",
        priority="high",
    ),
    BenefitProgram(
        name="Extra Help (Low Income Subsidy)",
        agency="Social Security Administration",
        description="Pays most Medicare drug plan (Part D) costs including premiums, deductibles, and co-pays.",
        eligibility_summary="Income below ~$20,000/year (individual) or ~$27,000/year (couple). Limited resources.",
        income_limit_note="Income and resource limits updated annually. Many people qualify automatically.",
        how_to_apply="Apply at SSA.gov, call 1-800-772-1213, or visit your local SSA office.",
        phone="1-800-772-1213",
        website="https://www.ssa.gov/medicare/part-d",
        category="medicare",
        apply_url="https://www.ssa.gov/i1020/",
        priority="high",
    ),
    BenefitProgram(
        name="Medicaid",
        agency="State Medicaid Agency",
        description="Pays for healthcare costs not covered by Medicare including nursing home care.",
        eligibility_summary="Based on income, age (65+), disability, and state rules. Many seniors qualify.",
        income_limit_note="Limits vary widely by state. Some states allow higher income with spend-down.",
        how_to_apply="Contact your state Medicaid office or apply at healthcare.gov.",
        phone="1-877-267-2323",
        website="https://www.medicaid.gov/medicaid/eligibility/index.html",
        category="medicaid",
        apply_url="https://www.healthcare.gov/medicaid-chip/",
        priority="high",
    ),
    BenefitProgram(
        name="Supplemental Security Income (SSI)",
        agency="Social Security Administration",
        description="Monthly cash payments for seniors 65+ and disabled people with limited income and resources.",
        eligibility_summary="Age 65+ or disabled. Very limited income (under ~$950/month) and resources (under $2,000).",
        income_limit_note="Federal benefit rate in 2024: $943/month for individuals. States may add supplement.",
        how_to_apply="Apply at SSA.gov or call 1-800-772-1213.",
        phone="1-800-772-1213",
        website="https://www.ssa.gov/ssi/",
        category="ssi",
        apply_url="https://www.ssa.gov/benefits/ssi/",
        priority="high",
    ),
    BenefitProgram(
        name="SNAP (Food Assistance)",
        agency="USDA Food and Nutrition Service",
        description="Monthly benefit to help pay for groceries. Average senior benefit: $80–$200/month.",
        eligibility_summary="Income below 130% of poverty level (~$1,580/month for 1 person in 2024).",
        income_limit_note="Seniors with high medical expenses may deduct them, making more people eligible.",
        how_to_apply="Apply at your local SNAP office or online through your state agency.",
        phone="1-800-221-5689",
        website="https://www.fns.usda.gov/snap/eligibility",
        category="food",
        apply_url="https://www.benefits.gov/benefit/361",
        priority="medium",
    ),
    BenefitProgram(
        name="LIHEAP (Energy Assistance)",
        agency="Department of Health & Human Services",
        description="Helps pay heating and cooling bills. One-time or seasonal payments.",
        eligibility_summary="Income at or below 150% of poverty level or 60% of state median income.",
        income_limit_note="~$1,900/month for 1 person. Benefits vary by state and available funding.",
        how_to_apply="Contact your local Community Action Agency or state LIHEAP office.",
        phone="1-866-674-6327",
        website="https://www.acf.hhs.gov/ocs/programs/liheap",
        category="energy",
        apply_url="https://www.benefits.gov/benefit/623",
        priority="medium",
    ),
    BenefitProgram(
        name="Veterans Benefits (VA)",
        agency="Department of Veterans Affairs",
        description="Healthcare, pension, disability compensation, and other benefits for veterans.",
        eligibility_summary="Must have served in US military. Discharge must be other than dishonorable.",
        income_limit_note="Many benefits are not income-based. Non-service-connected pension has income limits.",
        how_to_apply="Apply at VA.gov, call 1-800-827-1000, or visit your local VA office.",
        phone="1-800-827-1000",
        website="https://www.va.gov/benefits/",
        category="veterans",
        apply_url="https://www.va.gov/decision-reviews/",
        priority="high",
    ),
    BenefitProgram(
        name="Social Security Disability (SSDI)",
        agency="Social Security Administration",
        description="Monthly benefits for people with disabilities who have worked and paid Social Security taxes.",
        eligibility_summary="Must have a qualifying disability expected to last 12+ months or result in death. Work history required.",
        income_limit_note="Substantial Gainful Activity limit: $1,550/month (2024) for non-blind.",
        how_to_apply="Apply at SSA.gov, call 1-800-772-1213.",
        phone="1-800-772-1213",
        website="https://www.ssa.gov/disability/",
        category="disability",
        apply_url="https://www.ssa.gov/benefits/disability/apply.html",
        priority="high",
    ),
    BenefitProgram(
        name="Property Tax Relief",
        agency="State/County Tax Authority",
        description="Many states and counties offer property tax exemptions or deferrals for seniors 65+.",
        eligibility_summary="Usually age 65+, primary residence, income limits vary by county.",
        income_limit_note="Highly variable by state and county. Worth checking even if you think you don't qualify.",
        how_to_apply="Contact your county tax assessor or appraisal district.",
        phone="Contact your county appraisal district",
        website="https://www.ncsl.org/research/fiscal-policy/property-tax-relief-for-homeowners.aspx",
        category="property",
        apply_url="",
        priority="medium",
    ),
    BenefitProgram(
        name="State Pharmaceutical Assistance (SPAP)",
        agency="State Health Department",
        description="Many states offer drug assistance programs for seniors who still have high drug costs after Medicare.",
        eligibility_summary="Varies by state. Usually income-based. Must have Medicare Part D.",
        income_limit_note="Varies widely by state. Some have no income limit.",
        how_to_apply="Contact your State Health Insurance Assistance Program (SHIP).",
        phone="1-877-839-2675",
        website="https://www.medicare.gov/plan-compare/#/?lang=en",
        category="medication",
        apply_url="https://www.medicare.gov/talk-to-someone",
        priority="medium",
    ),
]


def check_benefits_eligibility(user_profile: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Check which benefits a senior may be eligible for based on their profile.

    user_profile should contain:
      - age (int)
      - monthly_income (float)
      - is_veteran (bool)
      - has_medicare (bool)
      - has_medicaid (bool)
      - state (str)
      - owns_home (bool)
      - has_disability (bool)
    """
    age = user_profile.get("age", 65)
    monthly_income = user_profile.get("monthly_income", 0)
    is_veteran = user_profile.get("is_veteran", False)
    has_medicare = user_profile.get("has_medicare", True)
    has_medicaid = user_profile.get("has_medicaid", False)
    has_disability = user_profile.get("has_disability", False)
    owns_home = user_profile.get("owns_home", False)

    results = []
    for program in ALL_PROGRAMS:
        p = program

        # Skip VA if not a veteran
        if p.category == "veterans" and not is_veteran:
            continue

        # Skip if already has Medicaid
        if p.name == "Medicaid" and has_medicaid:
            continue

        # Skip MSP/Extra Help if no Medicare
        if p.category == "medicare" and not has_medicare:
            continue

        # Skip property tax if doesn't own home
        if p.category == "property" and not owns_home:
            continue

        # Determine potential eligibility
        potentially_eligible = False
        if monthly_income > 0:
            if monthly_income < 1600 and p.category in ("medicare", "medicaid", "ssi"):
                potentially_eligible = True
            elif monthly_income < 1900 and p.category == "energy":
                potentially_eligible = True
            elif monthly_income < 1600 and p.category == "food":
                potentially_eligible = True
            elif p.category in ("veterans", "property", "medication", "disability"):
                potentially_eligible = True
        else:
            # No income info — show all as potentially eligible
            potentially_eligible = True

        if potentially_eligible:
            results.append({
                "name": p.name,
                "agency": p.agency,
                "description": p.description,
                "eligibility_summary": p.eligibility_summary,
                "income_limit_note": p.income_limit_note,
                "how_to_apply": p.how_to_apply,
                "phone": p.phone,
                "website": p.website,
                "apply_url": p.apply_url,
                "category": p.category,
                "priority": p.priority,
                "potentially_eligible": True,
            })

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    results.sort(key=lambda x: priority_order.get(x["priority"], 1))

    return results


def get_all_programs() -> list[dict[str, Any]]:
    """Return all available benefit programs."""
    return [
        {
            "name": p.name,
            "agency": p.agency,
            "description": p.description,
            "eligibility_summary": p.eligibility_summary,
            "how_to_apply": p.how_to_apply,
            "phone": p.phone,
            "website": p.website,
            "apply_url": p.apply_url,
            "category": p.category,
            "priority": p.priority,
        }
        for p in ALL_PROGRAMS
    ]


DISCLAIMER = (
    "This information is for general guidance only and may not reflect the most current eligibility rules. "
    "Benefit programs change frequently. Always verify your eligibility directly with the relevant agency "
    "before applying. A free Benefits Counselor through your local Area Agency on Aging can help you "
    "navigate these programs at no cost. Call the Eldercare Locator at 1-800-677-1116."
)
