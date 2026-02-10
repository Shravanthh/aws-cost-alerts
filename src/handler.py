import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_ssm_client = boto3.client("ssm")


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


def lambda_handler(event, context):
    logger.info("Received event: %s", json.dumps(event))

    budget_amount = _get_budget_amount()

    response = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "archive_enabled": os.getenv("ARCHIVE_ENABLED", "false"),
        "budget_param_name": os.getenv("BUDGET_PARAM_NAME", ""),
        "budget_amount": str(budget_amount) if budget_amount is not None else None,
    }

    return {
        "statusCode": 200,
        "body": json.dumps(response),
    }
