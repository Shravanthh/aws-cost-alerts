"""Alert calculations — budget thresholds and daily anomaly detection."""

from decimal import Decimal


def check_budget_thresholds(mtd_amount, budget_amount, thresholds, credits_used=Decimal("0")):
    """Return list of triggered budget threshold alerts."""
    if budget_amount is None or budget_amount <= 0:
        return []
    if not isinstance(mtd_amount, Decimal):
        return []
    net = mtd_amount - credits_used
    if net <= 0:
        return []
    pct = (net / budget_amount) * 100
    return [
        {"type": "BUDGET_THRESHOLD", "threshold_percent": t, "percent_used": pct}
        for t in thresholds if pct >= t
    ]


def check_daily_anomaly(daily_costs, threshold_percent):
    """Detect if latest day cost is anomalously high vs recent average."""
    if not daily_costs or len(daily_costs) < 2:
        return None
    latest = daily_costs[-1]
    history = [e["amount"] for e in daily_costs[:-1] if isinstance(e.get("amount"), Decimal)]
    if not history:
        return None
    avg = sum(history) / len(history)
    if avg == 0:
        return None
    latest_amt = latest.get("amount")
    if not isinstance(latest_amt, Decimal):
        return None
    pct_over = ((latest_amt - avg) / avg) * 100
    if pct_over < threshold_percent:
        return None
    return {
        "type": "DAILY_ANOMALY",
        "date": latest.get("date"),
        "amount": latest_amt,
        "average": avg,
        "percent_over_average": pct_over,
        "threshold_percent": threshold_percent,
    }
