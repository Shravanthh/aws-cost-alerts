import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_ssm_client = boto3.client("ssm")
_ce_client = boto3.client("ce")

DEFAULT_METRIC = os.getenv("COST_METRIC", "UnblendedCost")
DEFAULT_TOP_SERVICES = 10
FORECAST_METRIC_MAP = {
    "UnblendedCost": "UNBLENDED_COST",
    "BlendedCost": "BLENDED_COST",
    "AmortizedCost": "AMORTIZED_COST",
    "NetAmortizedCost": "NET_AMORTIZED_COST",
    "NetUnblendedCost": "NET_UNBLENDED_COST",
}


def _get_budget_amount():
    param_name = os.getenv("BUDGET_PARAM_NAME", "").strip()
    if not param_name:
        logger.warning("BUDGET_PARAM_NAME is not set.")
        return None

    try:
        response = _ssm_client.get_parameter(Name=param_name, WithDecryption=False)
    except ClientError as exc:
        logger.error("Failed to read SSM parameter %s: %s", param_name, exc)
        return None

    raw_value = response.get("Parameter", {}).get("Value", "")
    if raw_value == "":
        logger.warning("SSM parameter %s is empty.", param_name)
        return None

    try:
        return Decimal(raw_value)
    except InvalidOperation:
        logger.error("SSM parameter %s is not a valid number: %r", param_name, raw_value)
        return None


def _get_int_env(name, default):
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        logger.warning("Invalid %s value %r; using default %s.", name, raw_value, default)
        return default
    if parsed <= 0:
        logger.warning("Invalid %s value %r; using default %s.", name, raw_value, default)
        return default
    return parsed


def _sum_cost_and_usage(results, metric):
    total = Decimal("0")
    unit = None
    for entry in results:
        cost_info = entry.get("Total", {}).get(metric, {})
        amount = cost_info.get("Amount")
        unit = cost_info.get("Unit", unit)
        if amount is None:
            continue
        try:
            total += Decimal(amount)
        except InvalidOperation:
            logger.warning("Invalid cost amount encountered: %r", amount)
    return total, unit


def _get_month_time_period(today):
    start_date = today.replace(day=1)
    end_date = today
    if end_date <= start_date:
        end_date = start_date + timedelta(days=1)
    return start_date.isoformat(), end_date.isoformat()


def _get_month_to_date_cost(today, metric):
    start, end = _get_month_time_period(today)
    response = _ce_client.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="MONTHLY",
        Metrics=[metric],
    )
    results = response.get("ResultsByTime", [])
    total, unit = _sum_cost_and_usage(results, metric)
    return {
        "start": start,
        "end": end,
        "amount": total,
        "unit": unit,
    }


def _get_service_breakdown(today, metric, max_services):
    start, end = _get_month_time_period(today)
    groups = []
    next_token = None
    while True:
        request = {
            "TimePeriod": {"Start": start, "End": end},
            "Granularity": "MONTHLY",
            "Metrics": [metric],
            "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
        }
        if next_token:
            request["NextPageToken"] = next_token
        response = _ce_client.get_cost_and_usage(**request)
        results = response.get("ResultsByTime", [])
        if results:
            groups.extend(results[0].get("Groups", []))
        next_token = response.get("NextPageToken")
        if not next_token:
            break

    if not groups:
        return {"start": start, "end": end, "total": Decimal("0"), "unit": None, "services": []}
    services = []
    total = Decimal("0")
    unit = None
    for group in groups:
        keys = group.get("Keys", [])
        service_name = keys[0] if keys else "Unknown"
        cost_info = group.get("Metrics", {}).get(metric, {})
        amount = cost_info.get("Amount")
        unit = cost_info.get("Unit", unit)
        if amount is None:
            continue
        try:
            amount_value = Decimal(amount)
        except InvalidOperation:
            logger.warning("Invalid service amount for %s: %r", service_name, amount)
            continue
        total += amount_value
        services.append(
            {
                "service": service_name,
                "amount": amount_value,
                "unit": unit,
            }
        )

    services.sort(key=lambda item: item["amount"], reverse=True)
    top_services = services[:max_services]
    if total > 0:
        for entry in top_services:
            entry["percent_of_total"] = (entry["amount"] / total) * Decimal("100")
    else:
        for entry in top_services:
            entry["percent_of_total"] = Decimal("0")

    return {
        "start": start,
        "end": end,
        "total": total,
        "unit": unit,
        "services": top_services,
    }


def _get_previous_day_cost(today, metric):
    start_date = today - timedelta(days=1)
    start = start_date.isoformat()
    end = today.isoformat()
    response = _ce_client.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="DAILY",
        Metrics=[metric],
    )
    results = response.get("ResultsByTime", [])
    total, unit = _sum_cost_and_usage(results, metric)
    return {
        "start": start,
        "end": end,
        "amount": total,
        "unit": unit,
    }


def _get_month_end(today):
    if today.month == 12:
        return date(today.year + 1, 1, 1)
    return date(today.year, today.month + 1, 1)


def _get_forecast_cost(today, metric):
    start = today.isoformat()
    end = _get_month_end(today).isoformat()
    forecast_metric = FORECAST_METRIC_MAP.get(metric, "UNBLENDED_COST")
    response = _ce_client.get_cost_forecast(
        TimePeriod={"Start": start, "End": end},
        Metric=forecast_metric,
        Granularity="MONTHLY",
    )
    total = response.get("Total", {})
    amount = total.get("Amount")
    unit = total.get("Unit")
    lower = response.get("PredictionIntervalLowerBound")
    upper = response.get("PredictionIntervalUpperBound")
    return {
        "start": start,
        "end": end,
        "amount": Decimal(amount) if amount is not None else None,
        "unit": unit,
        "prediction_interval": {
            "lower": Decimal(lower) if lower is not None else None,
            "upper": Decimal(upper) if upper is not None else None,
        },
    }


def _stringify_cost_payload(payload):
    if payload is None:
        return None
    formatted = payload.copy()
    if isinstance(formatted.get("amount"), Decimal):
        formatted["amount"] = str(formatted["amount"])
    prediction = formatted.get("prediction_interval")
    if isinstance(prediction, dict):
        lower = prediction.get("lower")
        upper = prediction.get("upper")
        if isinstance(lower, Decimal):
            prediction["lower"] = str(lower)
        if isinstance(upper, Decimal):
            prediction["upper"] = str(upper)
    return formatted


def _stringify_service_breakdown(payload):
    if payload is None:
        return None
    formatted = payload.copy()
    if isinstance(formatted.get("total"), Decimal):
        formatted["total"] = str(formatted["total"])
    services = []
    for entry in formatted.get("services", []):
        service_entry = entry.copy()
        if isinstance(service_entry.get("amount"), Decimal):
            service_entry["amount"] = str(service_entry["amount"])
        if isinstance(service_entry.get("percent_of_total"), Decimal):
            service_entry["percent_of_total"] = str(service_entry["percent_of_total"])
        services.append(service_entry)
    formatted["services"] = services
    return formatted


def lambda_handler(event, context):
    logger.info("Received event: %s", json.dumps(event))

    budget_amount = _get_budget_amount()
    today = datetime.now(timezone.utc).date()
    top_services_count = _get_int_env("TOP_SERVICES_COUNT", DEFAULT_TOP_SERVICES)

    try:
        month_to_date = _get_month_to_date_cost(today, DEFAULT_METRIC)
        previous_day = _get_previous_day_cost(today, DEFAULT_METRIC)
        forecast = _get_forecast_cost(today, DEFAULT_METRIC)
        service_breakdown = _get_service_breakdown(today, DEFAULT_METRIC, top_services_count)
    except ClientError as exc:
        logger.error("Cost Explorer API error: %s", exc)
        month_to_date = None
        previous_day = None
        forecast = None
        service_breakdown = None

    response = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "archive_enabled": os.getenv("ARCHIVE_ENABLED", "false"),
        "budget_param_name": os.getenv("BUDGET_PARAM_NAME", ""),
        "budget_amount": str(budget_amount) if budget_amount is not None else None,
        "metric": DEFAULT_METRIC,
        "month_to_date": _stringify_cost_payload(month_to_date),
        "previous_day": _stringify_cost_payload(previous_day),
        "forecast": _stringify_cost_payload(forecast),
        "service_breakdown": _stringify_service_breakdown(service_breakdown),
    }

    return {
        "statusCode": 200,
        "body": json.dumps(response),
    }
