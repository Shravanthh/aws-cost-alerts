"""AWS Cost Explorer queries — each function does one query."""

import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import boto3
from botocore.exceptions import ClientError

from config import CREDIT_FILTER, EXCLUDE_RECORD_TYPES, FORECAST_METRIC_MAP

logger = logging.getLogger(__name__)

_ce = boto3.client("ce")


def _month_period(today):
    return today.replace(day=1).isoformat(), today.isoformat()


def _month_end(today):
    return date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)


def _parse_amount(raw):
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        logger.warning("Invalid cost amount: %r", raw)
        return None


def _sum_results(results, metric):
    total, unit = Decimal("0"), None
    for entry in results:
        info = entry.get("Total", {}).get(metric, {})
        amount = _parse_amount(info.get("Amount"))
        unit = info.get("Unit", unit)
        if amount is not None:
            total += amount
    return total, unit


def _cost_result(start, end, total, unit):
    return {"start": start, "end": end, "amount": total, "unit": unit}


def get_monthly_daily_breakdown(today, metric, trend_days):
    """Single API call: daily granularity for the month. Derives MTD, previous day, and trend."""
    start, end = _month_period(today)
    if start == end:
        return {
            "month_to_date": _cost_result(start, end, Decimal("0"), "USD"),
            "previous_day": _cost_result(start, end, Decimal("0"), "USD"),
            "daily_costs": [],
        }
    resp = _ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="DAILY",
        Metrics=[metric],
        Filter=EXCLUDE_RECORD_TYPES,
    )
    all_days, mtd_total, unit = [], Decimal("0"), None
    for entry in resp.get("ResultsByTime", []):
        info = entry.get("Total", {}).get(metric, {})
        amount = _parse_amount(info.get("Amount"))
        unit = info.get("Unit", unit)
        if amount is not None:
            mtd_total += amount
            all_days.append({
                "date": entry.get("TimePeriod", {}).get("Start"),
                "amount": amount,
                "unit": unit,
            })

    prev = all_days[-1] if all_days else {"amount": Decimal("0"), "unit": unit or "USD"}
    trend = all_days[-trend_days:] if len(all_days) > trend_days else all_days

    return {
        "month_to_date": _cost_result(start, end, mtd_total, unit),
        "previous_day": _cost_result(
            prev.get("date", end), end, prev.get("amount", Decimal("0")), prev.get("unit", unit),
        ),
        "daily_costs": trend,
    }


def get_month_to_date(today, metric):
    """Standalone MTD query — used by cost_monitor."""
    start, end = _month_period(today)
    if start == end:
        return _cost_result(start, end, Decimal("0"), "USD")
    resp = _ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="MONTHLY",
        Metrics=[metric],
        Filter=EXCLUDE_RECORD_TYPES,
    )
    total, unit = _sum_results(resp.get("ResultsByTime", []), metric)
    return _cost_result(start, end, total, unit)


def get_credit_usage(today, metric):
    """Credits and discounts applied this month."""
    start, end = _month_period(today)
    if start == end:
        return {"credits_used": Decimal("0"), "unit": "USD"}
    resp = _ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="MONTHLY",
        Metrics=[metric],
        Filter=CREDIT_FILTER,
    )
    total, unit = _sum_results(resp.get("ResultsByTime", []), metric)
    return {"credits_used": abs(total), "unit": unit or "USD"}


def get_forecast(today, metric):
    """Remaining month forecast from today to month end."""
    start = today.isoformat()
    end = _month_end(today).isoformat()
    forecast_metric = FORECAST_METRIC_MAP.get(metric, "UNBLENDED_COST")
    resp = _ce.get_cost_forecast(
        TimePeriod={"Start": start, "End": end},
        Metric=forecast_metric,
        Granularity="MONTHLY",
    )
    total = resp.get("Total", {})
    return {
        "start": start,
        "end": end,
        "amount": _parse_amount(total.get("Amount")),
        "unit": total.get("Unit"),
    }


def get_week_over_week(today, metric):
    """Compare this week's spend (Mon–today) vs same days last week."""
    weekday = today.weekday()  # 0=Mon
    this_week_start = today - timedelta(days=weekday)
    last_week_start = this_week_start - timedelta(days=7)
    last_week_end = last_week_start + timedelta(days=weekday)

    this_start = this_week_start.isoformat()
    this_end = today.isoformat()

    # On Monday, start == end — no data for this week yet
    if this_start == this_end:
        return {"this_week": Decimal("0"), "last_week": Decimal("0"), "change_pct": None, "unit": "USD"}

    resp = _ce.get_cost_and_usage(
        TimePeriod={"Start": this_start, "End": this_end},
        Granularity="MONTHLY",
        Metrics=[metric],
        Filter=EXCLUDE_RECORD_TYPES,
    )
    this_total, unit = _sum_results(resp.get("ResultsByTime", []), metric)

    lw_start = last_week_start.isoformat()
    lw_end = last_week_end.isoformat()
    if lw_start == lw_end:
        return {"this_week": this_total, "last_week": Decimal("0"), "change_pct": None, "unit": unit or "USD"}

    resp = _ce.get_cost_and_usage(
        TimePeriod={"Start": lw_start, "End": lw_end},
        Granularity="MONTHLY",
        Metrics=[metric],
        Filter=EXCLUDE_RECORD_TYPES,
    )
    last_total, unit = _sum_results(resp.get("ResultsByTime", []), metric)

    change_pct = None
    if last_total > 0:
        change_pct = ((this_total - last_total) / last_total) * 100

    return {
        "this_week": this_total,
        "last_week": last_total,
        "change_pct": change_pct,
        "unit": unit or "USD",
    }


def get_credit_daily_history(today, metric, days=14):
    """Get daily credit amounts to calculate burn rate."""
    start = (today - timedelta(days=days)).isoformat()
    end = today.isoformat()
    resp = _ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="DAILY",
        Metrics=[metric],
        Filter=CREDIT_FILTER,
    )
    daily_credits = []
    for entry in resp.get("ResultsByTime", []):
        info = entry.get("Total", {}).get(metric, {})
        amount = _parse_amount(info.get("Amount"))
        if amount is not None:
            daily_credits.append(abs(amount))
    return daily_credits


def get_service_breakdown(today, metric, max_services):
    """Top services by cost for the current month excluding credits."""
    start, end = _month_period(today)
    if start == end:
        return {"total": Decimal("0"), "unit": "USD", "services": []}

    groups, token = [], None
    while True:
        req = {
            "TimePeriod": {"Start": start, "End": end},
            "Granularity": "MONTHLY",
            "Metrics": [metric],
            "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
            "Filter": EXCLUDE_RECORD_TYPES,
        }
        if token:
            req["NextPageToken"] = token
        resp = _ce.get_cost_and_usage(**req)
        results = resp.get("ResultsByTime", [])
        if results:
            groups.extend(results[0].get("Groups", []))
        token = resp.get("NextPageToken")
        if not token:
            break

    services, total, unit = [], Decimal("0"), None
    for g in groups:
        name = g.get("Keys", ["Unknown"])[0]
        amount = _parse_amount(g.get("Metrics", {}).get(metric, {}).get("Amount"))
        unit = g.get("Metrics", {}).get(metric, {}).get("Unit", unit)
        if amount is not None:
            total += amount
            services.append({"service": name, "amount": amount, "unit": unit})

    services.sort(key=lambda s: s["amount"], reverse=True)
    top = services[:max_services]
    for s in top:
        s["percent_of_total"] = (s["amount"] / total * 100) if total > 0 else Decimal("0")

    return {"total": total, "unit": unit, "services": top}
