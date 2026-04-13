from __future__ import annotations

from datetime import datetime, timezone
from collections import Counter

from sqlalchemy.orm import Session, joinedload

from app.models.deal import Deal
from app.models.memo import Memo
from app.utils.org_scope import active_query


def _fmt_currency(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def _fmt_float(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}"


def _recommendation(score: float | None) -> str:
    if score is None:
        return "Not available (deal has not been scored)"
    if score >= 70:
        return "Strong Buy"
    if score >= 50:
        return "Conditional Buy"
    if score >= 30:
        return "Watch"
    return "Pass"


def generate_memo_content(deal: Deal) -> str:
    """Build markdown memo from a fully-loaded Deal ORM object."""

    outputs = deal.outputs
    contacts = deal.contacts or []
    activities = deal.activities or []
    signals = deal.signals or []

    # --- 1. Executive Summary ---
    lines: list[str] = []
    lines.append(f"# Investment Memo: {deal.name}")
    lines.append("")
    lines.append(f"*Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*")
    lines.append("")
    lines.append("## 1. Executive Summary")
    lines.append("")
    lines.append(f"- **Deal Name:** {deal.name}")
    lines.append(f"- **Address:** {deal.address or 'N/A'}")
    if deal.city or deal.state or deal.zip_code:
        parts = [p for p in [deal.city, deal.state, deal.zip_code] if p]
        lines.append(f"- **Location:** {', '.join(parts)}")
    lines.append(f"- **Property Type:** {deal.property_type or 'N/A'}")
    lines.append(f"- **Asking Price:** {_fmt_currency(deal.asking_price)}")
    lines.append(f"- **Status:** {deal.status.value if deal.status else 'N/A'}")
    lines.append(f"- **Score:** {_fmt_float(deal.score, 1) if deal.score is not None else 'N/A'}")

    # --- 2. Property Overview ---
    lines.append("")
    lines.append("## 2. Property Overview")
    lines.append("")
    lines.append(f"- **Units:** {deal.units if deal.units is not None else 'N/A'}")
    lines.append(f"- **Square Footage:** {f'{deal.sq_ft:,}' if deal.sq_ft is not None else 'N/A'}")
    lines.append(f"- **Year Built:** {deal.year_built if deal.year_built is not None else 'N/A'}")
    lines.append(f"- **Source:** {deal.source or 'N/A'}")

    # --- 3. Financial Summary ---
    lines.append("")
    lines.append("## 3. Financial Summary")
    lines.append("")
    if outputs:
        lines.append(f"- **Purchase Price:** {_fmt_currency(outputs.total_project_cost)}")
        lines.append(f"- **NOI:** {_fmt_currency(outputs.noi)}")
        lines.append(f"- **Cap Rate:** {_fmt_pct(outputs.cap_rate)}")
        lines.append(f"- **DSCR:** {_fmt_float(outputs.dscr)}x")
        lines.append(f"- **Cash-on-Cash Return:** {_fmt_pct(outputs.cash_on_cash)}")
        lines.append(f"- **IRR:** {_fmt_pct(outputs.irr)}")
        lines.append(f"- **Equity Multiple:** {_fmt_float(outputs.equity_multiple)}x")
        lines.append(f"- **Net Cash Flow:** {_fmt_currency(outputs.net_cash_flow)}")
        lines.append(f"- **Exit Value:** {_fmt_currency(outputs.exit_value)}")
        lines.append(f"- **Profit:** {_fmt_currency(outputs.profit)}")
    else:
        lines.append("*Financial outputs have not been computed for this deal.*")

    # --- 4. Risk Assessment ---
    lines.append("")
    lines.append("## 4. Risk Assessment")
    lines.append("")
    lines.append(f"- **Risk Level:** {deal.risk_level.value.title() if deal.risk_level else 'N/A'}")
    lines.append(f"- **Score:** {_fmt_float(deal.score, 1) if deal.score is not None else 'N/A'}")
    if signals:
        lines.append(f"- **Signals ({len(signals)}):**")
        for sig in signals:
            severity_str = f" (severity: {_fmt_float(sig.severity)})" if sig.severity is not None else ""
            lines.append(f"  - {sig.signal_type}: {sig.description or 'No description'}{severity_str}")
    else:
        lines.append("- **Signals:** None recorded")

    # --- 5. Contact Summary ---
    lines.append("")
    lines.append("## 5. Contact Summary")
    lines.append("")
    if contacts:
        status_counts = Counter(c.status.value for c in contacts)
        lines.append(f"- **Total Contacts:** {len(contacts)}")
        for status, count in sorted(status_counts.items()):
            lines.append(f"  - {status.replace('_', ' ').title()}: {count}")
    else:
        lines.append("*No contacts associated with this deal.*")

    # --- 6. Activity Log Summary ---
    lines.append("")
    lines.append("## 6. Activity Log Summary")
    lines.append("")
    if activities:
        type_counts = Counter(a.activity_type.value for a in activities)
        lines.append(f"- **Total Activities:** {len(activities)}")
        for atype, count in sorted(type_counts.items()):
            lines.append(f"  - {atype.title()}: {count}")
    else:
        lines.append("*No activities recorded for this deal.*")

    # --- 7. Recommendation ---
    lines.append("")
    lines.append("## 7. Recommendation")
    lines.append("")
    rec = _recommendation(deal.score)
    lines.append(f"**{rec}**")
    if deal.score is not None:
        lines.append(f"  (Based on deal score of {deal.score:.1f}/100)")
    lines.append("")

    return "\n".join(lines)


def generate_memo(db: Session, deal_id: str) -> Memo:
    """Generate (or regenerate) an investment memo for a deal.

    Loads all related data from the DB, builds markdown content,
    and creates or replaces the memo record.
    """
    deal = (
        active_query(db.query(Deal), Deal)
        .options(
            joinedload(Deal.assumptions),
            joinedload(Deal.outputs),
            joinedload(Deal.contacts),
            joinedload(Deal.activities),
            joinedload(Deal.signals),
        )
        .filter(Deal.id == deal_id)
        .first()
    )
    if deal is None:
        return None  # type: ignore[return-value]

    content = generate_memo_content(deal)
    title = f"Investment Memo - {deal.name}"

    existing_memo = deal.memo
    if existing_memo is not None:
        existing_memo.content = content
        existing_memo.title = title
        existing_memo.version = (existing_memo.version or 0) + 1
        existing_memo.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing_memo)
        return existing_memo

    memo = Memo(
        deal_id=deal_id,
        title=title,
        content=content,
        version=1,
    )
    memo.organization_id = deal.organization_id
    db.add(memo)
    db.commit()
    db.refresh(memo)
    return memo
