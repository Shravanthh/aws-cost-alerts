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
    return (
        date(today.year + 1, 1, 1)
        if today.month == 12
        else date(today.year, today.month + 1, 1)
    )


def _parse_amount(raw):
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        logger.warning("Invalid cost amount: %r", raw)
        return None


def _cost_result(start, end, total, unit):
    return {"start": start, "end": end, "amount": total, "unit": unit}


def get_daily_breakdown(today, metric, trend_days):
    """Single API call covering month + last week. Derives MTD, previous day, trend, and week-over-week."""
    month_start, end = _month_period(today)
    weekday = today.weekday()  # 0=Mon
    last_monday = today - timedelta(days=weekday + 7)
    query_start = min(date.fromisoformat(month_start), last_monday).isoformat()

    resp = _ce.get_cost_and_usage(
        TimePeriod={"Start": query_start, "End": end},
        Granularity="DAILY",
        Metrics=[metric],
        Filter=EXCLUDE_RECORD_TYPES,
    )

    daily_by_date, unit = {}, None
    for entry in resp.get("ResultsByTime", []):
        info = entry.get("Total", {}).get(metric, {})
        amount = _parse_amount(info.get("Amount"))
        unit = info.get("Unit", unit)
        d = entry.get("TimePeriod", {}).get("Start")
        if amount is not None and d:
            daily_by_date[d] = {"date": d, "amount": amount, "unit": unit}

    # MTD: only current month days
    mtd_days = [v for k, v in sorted(daily_by_date.items()) if k >= month_start]
    mtd_total = sum(d["amount"] for d in mtd_days)
    prev = mtd_days[-1] if mtd_days else {"date": end, "amount": Decimal("0"), "unit": unit or "USD"}
    trend = mtd_days[-trend_days:] if len(mtd_days) > trend_days else mtd_days

    # Week-over-week from same data
    this_monday = (today - timedelta(days=weekday)).isoformat()
    last_monday_str = last_monday.isoformat()
    last_week_end_str = (last_monday + timedelta(days=weekday)).isoformat()

    if weekday == 0:  # Monday — no data for this week yet
        this_total, last_total = Decimal("0"), Decimal("0")
        change_pct = None
    else:
        this_total = sum(v["amount"] for k, v in daily_by_date.items() if this_monday <= k < end)
        last_total = sum(v["amount"] for k, v in daily_by_date.items() if last_monday_str <= k < last_week_end_str)
        change_pct = ((this_total - last_total) / last_total * 100) if last_total > 0 else None

    return {
        "month_to_date": _cost_result(month_start, end, mtd_total, unit),
        "previous_day": _cost_result(prev["date"], end, prev["amount"], prev.get("unit", unit)),
        "daily_costs": trend,
        "week_over_week": {"this_week": this_total, "last_week": last_total, "change_pct": change_pct, "unit": unit or "USD"},
    }


def get_credit_info(today, metric, days=14):
    """Single API call: daily credits for last N days. Derives credits_used (this month) + daily_history."""
    month_start = today.replace(day=1).isoformat()
    start = (today - timedelta(days=days)).isoformat()
    end = today.isoformat()
    resp = _ce.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="DAILY",
        Metrics=[metric],
        Filter=CREDIT_FILTER,
    )
    credits_used, daily_history, unit = Decimal("0"), [], None
    for entry in resp.get("ResultsByTime", []):
        info = entry.get("Total", {}).get(metric, {})
        amount = _parse_amount(info.get("Amount"))
        unit = info.get("Unit", unit)
        d = entry.get("TimePeriod", {}).get("Start")
        if amount is not None:
            daily_history.append(abs(amount))
            if d and d >= month_start:
                credits_used += abs(amount)
    return {"credits_used": credits_used, "daily_history": daily_history, "unit": unit or "USD"}


def get_forecast(today, metric):
    """Remaining month forecast from today to month end."""
    start = (today + timedelta(days=1)).isoformat()
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
        s["percent_of_total"] = (
            (s["amount"] / total * 100) if total > 0 else Decimal("0")
        )

    return {"total": total, "unit": unit, "services": top}
