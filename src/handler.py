"""Lambda handler — orchestrates cost data collection, alerting, email, and archival."""

import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from botocore.exceptions import ClientError

import alerts
import archive
import config
import cost_explorer
import email_builder

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _safe_call(label, fn, *args, default=None):
    """Call fn(*args), log and return default on ClientError."""
    try:
        return fn(*args)
    except ClientError as exc:
        logger.error("Failed to %s: %s", label, exc)
        return default


def _collect_cost_data(today, cfg):
    """Fetch all cost data from Cost Explorer."""
    metric = cfg["metric"]
    return {
        "month_to_date": _safe_call("get MTD", cost_explorer.get_month_to_date, today, metric),
        "previous_day": _safe_call("get previous day", cost_explorer.get_previous_day, today, metric),
        "forecast": _safe_call("get forecast", cost_explorer.get_forecast, today, metric),
        "daily_costs": _safe_call("get daily costs", cost_explorer.get_daily_costs, today, metric, cfg["trend_days"], default=[]),
        "service_breakdown": _safe_call("get services", cost_explorer.get_service_breakdown, today, metric, cfg["top_services"]),
        "credit_info": _safe_call("get credits", cost_explorer.get_credit_usage, today, metric),
        "week_over_week": _safe_call("get WoW", cost_explorer.get_week_over_week, today, metric),
        "credit_daily_history": _safe_call("get credit history", cost_explorer.get_credit_daily_history, today, metric, default=[]),
    }


def _estimate_credit_exhaustion(today, data):
    """Estimate when credits will run out based on daily burn rate."""
    credit_info = data.get("credit_info")
    daily_history = data.get("credit_daily_history", [])
    if not credit_info or not daily_history:
        return None

    credits_used = credit_info.get("credits_used", Decimal("0"))
    if credits_used <= 0:
        return None

    avg_daily = sum(daily_history) / len(daily_history)
    if avg_daily <= 0:
        return None

    month_start = today.replace(day=1)
    month_end = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)
    days_in_month = (month_end - month_start).days
    days_elapsed = (today - month_start).days or 1

    return {
        "avg_daily_burn": avg_daily,
        "credits_used_so_far": credits_used,
        "projected_monthly_credits": avg_daily * days_in_month,
        "days_elapsed": days_elapsed,
        "days_remaining": days_in_month - days_elapsed,
        "unit": credit_info.get("unit", "USD"),
    }


def _compute_alerts(data, cfg):
    """Run all alert checks."""
    result = []
    mtd = data.get("month_to_date")
    credit_info = data.get("credit_info")
    credits_used = credit_info.get("credits_used", Decimal("0")) if credit_info else Decimal("0")

    if mtd:
        result.extend(alerts.check_budget_thresholds(
            mtd.get("amount"), cfg["budget_amount"], cfg["budget_thresholds"], credits_used,
        ))

    anomaly = alerts.check_daily_anomaly(data.get("daily_costs", []), cfg["anomaly_threshold"])
    if anomaly:
        result.append(anomaly)

    return result


def _send_report(email_content, cfg):
    """Send email, return (message_id, error)."""
    try:
        mid = email_builder.send(
            email_content["subject"],
            email_content["html"],
            email_content["text"],
            cfg["sender_email"],
            cfg["recipient_emails"],
        )
        return mid, None
    except (ClientError, ValueError) as exc:
        logger.error("Email send failed: %s", exc)
        return None, str(exc)


def _build_response(data, cfg, message_id, email_error, archive_key):
    """Assemble the Lambda response payload."""
    return {
        "status": "ok" if message_id else "partial",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metric": cfg["metric"],
        "budget_amount": str(cfg["budget_amount"]) if cfg["budget_amount"] else None,
        "ses_message_id": message_id,
        "email_error": email_error,
        "archive_key": archive_key,
    }


def lambda_handler(event, context):
    logger.info("Event: %s", json.dumps(event))

    cfg = config.load()
    today = datetime.now(timezone.utc).date()

    # 1. Collect cost data
    data = _collect_cost_data(today, cfg)

    # 2. Compute alerts
    data["alerts"] = _compute_alerts(data, cfg)

    # 2b. Compute credit estimate
    data["credit_estimate"] = _estimate_credit_exhaustion(today, data)

    # 3. Build and send email
    email_content = email_builder.build_email(today, data, cfg)
    message_id, email_error = _send_report(email_content, cfg)

    # 4. Archive
    archive_key = None
    if cfg["archive_enabled"]:
        archive_key = _safe_call("archive report", archive.archive_report, data, today, cfg["archive_bucket"])

    # 5. Response
    response = _build_response(data, cfg, message_id, email_error, archive_key)
    return {"statusCode": 200, "body": json.dumps(response, default=str)}
