"""Configuration loading from environment variables."""

import logging
import os
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_METRIC = "UnblendedCost"
DEFAULT_TOP_SERVICES = 10
DEFAULT_TREND_DAYS = 7
DEFAULT_ANOMALY_THRESHOLD_PERCENT = Decimal("30")
DEFAULT_BUDGET_THRESHOLDS = (
    Decimal("50"),
    Decimal("75"),
    Decimal("90"),
    Decimal("100"),
)

FORECAST_METRIC_MAP = {
    "UnblendedCost": "UNBLENDED_COST",
    "BlendedCost": "BLENDED_COST",
    "AmortizedCost": "AMORTIZED_COST",
    "NetAmortizedCost": "NET_AMORTIZED_COST",
    "NetUnblendedCost": "NET_UNBLENDED_COST",
}

EXCLUDE_RECORD_TYPES = {
    "Not": {
        "Dimensions": {
            "Key": "RECORD_TYPE",
            "Values": ["Credit", "Refund", "Enterprise Discount Program Discount"],
        }
    }
}

CREDIT_FILTER = {
    "Dimensions": {
        "Key": "RECORD_TYPE",
        "Values": ["Credit", "Enterprise Discount Program Discount"],
    }
}


def _get_int_env(name, default):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
        return val if val > 0 else default
    except ValueError:
        logger.warning("Invalid %s=%r, using default %s", name, raw, default)
        return default


def _get_decimal_env(name, default):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        val = Decimal(raw)
        return val if val > 0 else default
    except InvalidOperation:
        logger.warning("Invalid %s=%r, using default %s", name, raw, default)
        return default


def _get_thresholds_env(name, default):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    thresholds = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            val = Decimal(item)
            if val > 0:
                thresholds.append(val)
        except InvalidOperation:
            logger.warning("Invalid threshold %r in %s", item, name)
    return tuple(sorted(set(thresholds))) if thresholds else default


def get_budget_amount():
    """Read budget amount from environment variable."""
    raw = os.getenv("BUDGET_AMOUNT", "").strip()
    if not raw:
        return None
    try:
        val = Decimal(raw)
        return val if val > 0 else None
    except InvalidOperation:
        logger.error("BUDGET_AMOUNT=%r is not a valid number", raw)
        return None


def load():
    """Load all configuration into a dict."""
    return {
        "metric": os.getenv("COST_METRIC", DEFAULT_METRIC),
        "subject_prefix": os.getenv("EMAIL_SUBJECT_PREFIX", "AWS Cost Alert"),
        "sender_email": os.getenv("SENDER_EMAIL", "").strip(),
        "recipient_emails": [
            e.strip() for e in os.getenv("RECIPIENT_EMAILS", "").split(",") if e.strip()
        ],
        "archive_enabled": os.getenv("ARCHIVE_ENABLED", "true").lower() == "true",
        "archive_bucket": os.getenv("ARCHIVE_BUCKET", "").strip(),
        "top_services": _get_int_env("TOP_SERVICES_COUNT", DEFAULT_TOP_SERVICES),
        "trend_days": _get_int_env("TREND_DAYS", DEFAULT_TREND_DAYS),
        "anomaly_threshold": _get_decimal_env(
            "ANOMALY_THRESHOLD_PERCENT", DEFAULT_ANOMALY_THRESHOLD_PERCENT
        ),
        "budget_thresholds": _get_thresholds_env(
            "BUDGET_THRESHOLDS", DEFAULT_BUDGET_THRESHOLDS
        ),
        "budget_amount": get_budget_amount(),
    }
