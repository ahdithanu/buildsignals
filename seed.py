"""Seed the database with default org/user and 5 sample CRE deals."""

from app.db import init_db, SessionLocal
from app.models.organization import Organization
from app.models.user import User
from app.models.deal import Deal, DealStatus, RiskLevel
from app.models.deal_assumptions import DealAssumptions
from app.models.deal_outputs import DealOutputs
from app.models.contact import Contact, ContactStatus
from app.models.signal import Signal
from app.models.mixins import DEFAULT_ORG_ID
from app.services.normalization_service import normalize_property_type, normalize_signal_type

SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"


def _ensure_default_org_and_user(db):
    """Create the default organization and system user if they don't exist."""
    org = db.get(Organization, DEFAULT_ORG_ID)
    if not org:
        org = Organization(
            id=DEFAULT_ORG_ID,
            name="Default Organization",
            slug="default-org",
            is_active=True,
        )
        db.add(org)
        db.flush()
        print("  Created default organization.")

    user = db.get(User, SYSTEM_USER_ID)
    if not user:
        user = User(
            id=SYSTEM_USER_ID,
            email="system@dealsignal.local",
            full_name="System",
            password_hash="!nologin",
            is_active=True,
            is_superuser=False,
        )
        db.add(user)
        db.flush()
        print("  Created system user.")

    return org, user


def seed():
    init_db()
    db = SessionLocal()

    # Always ensure default org & system user exist
    _ensure_default_org_and_user(db)
    db.commit()

    # Check if deal data already exists
    if db.query(Deal).first():
        print("Database already seeded. Skipping deals.")
        db.close()
        return

    deals_data = [
        {
            "deal": dict(
                name="Parkview Multifamily Portfolio",
                address="1200 Parkview Blvd",
                city="Austin",
                state="TX",
                zip_code="78701",
                property_type="multifamily",
                units=240,
                sq_ft=196000,
                year_built=2015,
                asking_price=42_000_000,
                status=DealStatus.underwriting,
                risk_level=RiskLevel.low,
                score=82.5,
                source="CBRE Listing",
                notes="Class A garden-style community, 95% occupied, strong submarket fundamentals.",
            ),
            "assumptions": dict(
                purchase_price=41_000_000,
                closing_costs_pct=0.015,
                renovation_cost=1_200_000,
                loan_amount=28_700_000,
                interest_rate=0.0585,
                loan_term_years=30,
                gross_rental_income=4_800_000,
                vacancy_pct=0.05,
                opex_pct=0.38,
                cap_rate_market=0.055,
                exit_cap_rate=0.06,
                hold_period_years=5,
                rent_growth_pct=0.035,
            ),
            "contacts": [
                dict(name="Sarah Chen", role="Listing Broker", email="schen@cbre.com", phone="512-555-0101", company="CBRE"),
                dict(name="Michael Torres", role="Seller Representative", email="mtorres@hff.com", phone="512-555-0202", company="HFF"),
            ],
        },
        {
            "deal": dict(
                name="Downtown Office Tower - 500 Congress",
                address="500 Congress Ave",
                city="Dallas",
                state="TX",
                zip_code="75201",
                property_type="office",
                units=None,
                sq_ft=320000,
                year_built=2001,
                asking_price=78_000_000,
                status=DealStatus.ic_review,
                risk_level=RiskLevel.medium,
                score=71.0,
                source="JLL Off-Market",
                notes="Class A office, 82% leased, largest tenant lease expires in 18 months.",
            ),
            "assumptions": dict(
                purchase_price=75_000_000,
                closing_costs_pct=0.02,
                renovation_cost=5_000_000,
                loan_amount=48_750_000,
                interest_rate=0.065,
                loan_term_years=10,
                gross_rental_income=9_600_000,
                vacancy_pct=0.18,
                opex_pct=0.42,
                cap_rate_market=0.065,
                exit_cap_rate=0.07,
                hold_period_years=7,
                rent_growth_pct=0.025,
            ),
            "contacts": [
                dict(name="David Park", role="Asset Manager", email="dpark@jll.com", phone="214-555-0301", company="JLL"),
            ],
        },
        {
            "deal": dict(
                name="Sunset Strip Retail Center",
                address="8800 Sunset Blvd",
                city="Los Angeles",
                state="CA",
                zip_code="90069",
                property_type="retail",
                units=None,
                sq_ft=45000,
                year_built=1988,
                asking_price=18_500_000,
                status=DealStatus.loi_sent,
                risk_level=RiskLevel.medium,
                score=68.0,
                source="Marcus & Millichap",
                notes="Neighborhood retail center, NNN leases, 3 vacancies out of 12 suites.",
            ),
            "assumptions": dict(
                purchase_price=17_500_000,
                closing_costs_pct=0.02,
                renovation_cost=800_000,
                loan_amount=11_375_000,
                interest_rate=0.0625,
                loan_term_years=25,
                gross_rental_income=1_980_000,
                vacancy_pct=0.08,
                opex_pct=0.30,
                cap_rate_market=0.06,
                exit_cap_rate=0.065,
                hold_period_years=5,
                rent_growth_pct=0.02,
            ),
            "contacts": [],
        },
        {
            "deal": dict(
                name="Midwest Logistics Hub",
                address="4500 Industrial Pkwy",
                city="Indianapolis",
                state="IN",
                zip_code="46241",
                property_type="industrial",
                units=None,
                sq_ft=520000,
                year_built=2019,
                asking_price=56_000_000,
                status=DealStatus.qualified,
                risk_level=RiskLevel.low,
                score=88.0,
                source="Cushman & Wakefield",
                notes="Modern Class A logistics facility, cross-dock, 100% leased to investment-grade tenant.",
            ),
            "assumptions": dict(
                purchase_price=54_000_000,
                closing_costs_pct=0.015,
                renovation_cost=0,
                loan_amount=37_800_000,
                interest_rate=0.055,
                loan_term_years=30,
                gross_rental_income=4_160_000,
                vacancy_pct=0.03,
                opex_pct=0.22,
                cap_rate_market=0.05,
                exit_cap_rate=0.055,
                hold_period_years=10,
                rent_growth_pct=0.03,
            ),
            "contacts": [
                dict(name="Emily Washington", role="Leasing Agent", email="ewashington@cw.com", phone="317-555-0401", company="Cushman & Wakefield"),
                dict(name="Robert Kim", role="Tenant Contact", email="rkim@fedex.com", phone="317-555-0402", company="FedEx Logistics"),
            ],
        },
        {
            "deal": dict(
                name="Harbor Mixed-Use Development",
                address="200 Harbor Dr",
                city="San Diego",
                state="CA",
                zip_code="92101",
                property_type="mixed-use",
                units=150,
                sq_ft=185000,
                year_built=2022,
                asking_price=95_000_000,
                status=DealStatus.new,
                risk_level=RiskLevel.high,
                score=59.5,
                source="Broker Referral",
                notes="Ground-floor retail + 150 luxury apartments. Recently completed, lease-up phase.",
            ),
            "assumptions": dict(
                purchase_price=92_000_000,
                closing_costs_pct=0.02,
                renovation_cost=0,
                loan_amount=64_400_000,
                interest_rate=0.07,
                loan_term_years=30,
                gross_rental_income=7_200_000,
                vacancy_pct=0.15,
                opex_pct=0.35,
                cap_rate_market=0.045,
                exit_cap_rate=0.05,
                hold_period_years=5,
                rent_growth_pct=0.04,
            ),
            "contacts": [
                dict(name="Lisa Nakamura", role="Developer Contact", email="lnakamura@harbordev.com", phone="619-555-0501", company="Harbor Development Group"),
            ],
        },
    ]

    signals_data = [
        dict(signal_type="price_reduction", source="CoStar", description="Asking price reduced 5% from original listing", severity=6.0),
        dict(signal_type="tenant_risk", source="Moody's", description="Largest tenant credit downgrade", severity=8.0),
        dict(signal_type="market_trend", source="CBRE Research", description="Submarket vacancy trending down 200bps YoY", severity=3.0),
        dict(signal_type="new_construction", source="Dodge Data", description="850K SF competing supply delivering in 12 months", severity=7.5),
        dict(signal_type="lease_expiry", source="Internal", description="45% of NRA rolling in next 24 months", severity=7.0),
    ]

    org_id = DEFAULT_ORG_ID

    created_deals = []
    for item in deals_data:
        deal = Deal(**item["deal"])
        deal.organization_id = org_id
        deal.property_type = normalize_property_type(deal.property_type)
        db.add(deal)
        db.flush()

        assumptions = DealAssumptions(deal_id=deal.id, organization_id=org_id, **item["assumptions"])
        outputs = DealOutputs(deal_id=deal.id, organization_id=org_id)
        db.add(assumptions)
        db.add(outputs)

        for c in item["contacts"]:
            contact = Contact(deal_id=deal.id, organization_id=org_id, status=ContactStatus.not_contacted, **c)
            db.add(contact)

        created_deals.append(deal)

    # Attach signals to first 5 deals (one each)
    for i, sig in enumerate(signals_data):
        sig_copy = dict(sig)
        sig_copy["signal_type"] = normalize_signal_type(sig_copy["signal_type"]) or sig_copy["signal_type"]
        signal = Signal(deal_id=created_deals[i].id, organization_id=org_id, **sig_copy)
        db.add(signal)

    db.commit()
    db.close()
    print(f"Seeded {len(deals_data)} deals with assumptions, contacts, and signals.")


if __name__ == "__main__":
    seed()
