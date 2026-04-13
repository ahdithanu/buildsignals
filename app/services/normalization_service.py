from __future__ import annotations

"""Normalize free-text values to canonical sets."""

from typing import Optional

# Canonical property types
PROPERTY_TYPE_MAP = {
    "multifamily": "Multifamily",
    "multi-family": "Multifamily",
    "multi family": "Multifamily",
    "apartment": "Multifamily",
    "apartments": "Multifamily",
    "residential": "Multifamily",
    "retail": "Retail",
    "shopping": "Retail",
    "strip mall": "Retail",
    "shopping center": "Retail",
    "industrial": "Industrial",
    "warehouse": "Industrial",
    "logistics": "Industrial",
    "distribution": "Industrial",
    "mixed-use": "Mixed Use",
    "mixed use": "Mixed Use",
    "office": "Office",
    "flex": "Office",
}

SIGNAL_TYPE_MAP = {
    "permit": "Permit Activity",
    "permit_activity": "Permit Activity",
    "permit activity": "Permit Activity",
    "zoning": "Zoning Update",
    "zoning_update": "Zoning Update",
    "zoning update": "Zoning Update",
    "ownership": "Ownership Transfer",
    "ownership_transfer": "Ownership Transfer",
    "ownership transfer": "Ownership Transfer",
    "listing": "Broker Listing",
    "broker_listing": "Broker Listing",
    "broker listing": "Broker Listing",
    "market": "Market Trend",
    "market_trend": "Market Trend",
    "market trend": "Market Trend",
    # Price / valuation signals
    "price_reduction": "Price Reduction",
    "price reduction": "Price Reduction",
    "price_change": "Price Reduction",
    "price change": "Price Reduction",
    "price drop": "Price Reduction",
    # Tenant / occupancy signals
    "tenant_risk": "Tenant Risk",
    "tenant risk": "Tenant Risk",
    "tenant_default": "Tenant Risk",
    "vacancy": "Tenant Risk",
    "lease_expiry": "Lease Expiry",
    "lease expiry": "Lease Expiry",
    "lease_expiration": "Lease Expiry",
    "lease expiration": "Lease Expiry",
    # Construction / development signals
    "new_construction": "New Construction",
    "new construction": "New Construction",
    "development": "New Construction",
    "groundbreaking": "New Construction",
    # Distress signals
    "foreclosure": "Distress",
    "distress": "Distress",
    "default": "Distress",
    "bankruptcy": "Distress",
    # Regulatory
    "regulation": "Regulatory Change",
    "regulatory": "Regulatory Change",
    "tax_change": "Regulatory Change",
    "tax change": "Regulatory Change",
}


def normalize_property_type(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return raw
    key = raw.strip().lower()
    return PROPERTY_TYPE_MAP.get(key, raw)  # Return original if no match (don't reject)


def normalize_signal_type(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return raw
    key = raw.strip().lower()
    return SIGNAL_TYPE_MAP.get(key, raw)  # Return original if no match (don't reject)
