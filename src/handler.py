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


def _get_month_to_date_cost(today, metric):
    start_date = today.replace(day=1)
    end_date = today
    if end_date <= start_date:
        end_date = start_date + timedelta(days=1)
    start = start_date.isoformat()
    end = end_date.isoformat()
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


def lambda_handler(event, context):
    logger.info("Received event: %s", json.dumps(event))

    budget_amount = _get_budget_amount()
    today = datetime.now(timezone.utc).date()

    try:
        month_to_date = _get_month_to_date_cost(today, DEFAULT_METRIC)
        previous_day = _get_previous_day_cost(today, DEFAULT_METRIC)
        forecast = _get_forecast_cost(today, DEFAULT_METRIC)
    except ClientError as exc:
        logger.error("Cost Explorer API error: %s", exc)
        month_to_date = None
        previous_day = None
        forecast = None

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
    }

    return {
        "statusCode": 200,
        "body": json.dumps(response),
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
