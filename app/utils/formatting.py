"""Display formatting helpers for CRE data."""


def format_currency(value: float | None, decimals: int = 0) -> str:
    """Format a number as USD currency string."""
    if value is None:
        return "$0"
    if decimals == 0:
        return f"${value:,.0f}"
    return f"${value:,.{decimals}f}"


def format_percent(value: float | None, decimals: int = 1) -> str:
    """Format a decimal (0.065) as a percentage string ('6.5%')."""
    if value is None:
        return "0.0%"
    return f"{value * 100:,.{decimals}f}%"


def format_sqft(value: int | None) -> str:
    """Format square footage with comma separator."""
    if value is None:
        return "0 SF"
    return f"{value:,} SF"


def format_units(value: int | None) -> str:
    """Format unit count."""
    if value is None:
        return "0 units"
    return f"{value:,} unit{'s' if value != 1 else ''}"


def truncate(text: str | None, max_len: int = 100) -> str:
    """Truncate text with ellipsis."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
