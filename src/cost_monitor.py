"""Ad-hoc cost threshold monitor — runs every 6 hours, alerts if MTD exceeds threshold."""

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

import config
import cost_explorer
import email_builder as eb
from formatters import currency

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_ssm = boto3.client("ssm")

ALERT_STATE_PARAM = "/cost-alerts/last-alert-month"


def _already_alerted_this_month(today):
    """Check if we already sent a threshold alert this month."""
    try:
        resp = _ssm.get_parameter(Name=ALERT_STATE_PARAM, WithDecryption=False)
        return resp["Parameter"]["Value"] == today.strftime("%Y-%m")
    except ClientError:
        return False


def _mark_alerted(today):
    """Record that we sent an alert this month."""
    try:
        _ssm.put_parameter(
            Name=ALERT_STATE_PARAM,
            Value=today.strftime("%Y-%m"),
            Type="String",
            Overwrite=True,
        )
    except ClientError as exc:
        logger.warning("Failed to update alert state: %s", exc)


def lambda_handler(event, context):
    logger.info("Cost monitor event: %s", json.dumps(event))

    cfg = config.load()
    today = datetime.now(timezone.utc).date()
    metric = cfg["metric"]
    threshold = cfg["budget_amount"]

    if threshold is None or threshold <= 0:
        logger.info("No budget threshold configured, skipping.")
        return {"statusCode": 200, "body": "no threshold"}

    if _already_alerted_this_month(today):
        logger.info("Already alerted this month, skipping.")
        return {"statusCode": 200, "body": json.dumps({"alert": False, "reason": "already_alerted"})}

    try:
        mtd = cost_explorer.get_month_to_date(today, metric)
    except ClientError as exc:
        logger.error("Failed to get MTD: %s", exc)
        return {"statusCode": 500, "body": str(exc)}

    gross = mtd.get("amount", Decimal("0"))

    if gross <= threshold:
        logger.info("Gross MTD $%.2f is within threshold $%.2f", gross, threshold)
        return {"statusCode": 200, "body": json.dumps({"gross": str(gross), "threshold": str(threshold), "alert": False})}

    # Threshold breached — get credits for context
    try:
        credit_info = cost_explorer.get_credit_usage(today, metric)
    except ClientError:
        credit_info = {"credits_used": Decimal("0"), "unit": "USD"}

    credits_used = credit_info.get("credits_used", Decimal("0"))
    net = gross - credits_used
    unit = mtd.get("unit", "USD")

    subject = f"⚠ {cfg['subject_prefix']} - Cost Threshold Breached"
    html = _build_alert_html(today, gross, credits_used, net, threshold, unit)
    text = (
        f"Cost Threshold Alert - {today.isoformat()}\n\n"
        f"Monthly gross cost has exceeded {currency(threshold, unit)}\n"
        f"Gross MTD: {currency(gross, unit)}\n"
        f"Credits: -{currency(credits_used, unit)}\n"
        f"Net Cost: {currency(net, unit)}\n"
        f"Threshold: {currency(threshold, unit)}"
    )

    message_id = None
    try:
        message_id = eb.send(subject, html, text, cfg["sender_email"], cfg["recipient_emails"])
        _mark_alerted(today)
    except (ClientError, ValueError) as exc:
        logger.error("Failed to send alert: %s", exc)

    return {
        "statusCode": 200,
        "body": json.dumps({"gross": str(gross), "net": str(net), "threshold": str(threshold), "alert": True, "ses_message_id": message_id}, default=str),
    }


def _build_alert_html(today, gross, credits_used, net, threshold, unit):
    return (
        '<html><body style="font-family:-apple-system,Arial,sans-serif;color:#1a1a1a;'
        'background:#f0f2f5;margin:0;padding:0;">'
        '<div style="max-width:640px;margin:0 auto;padding:20px;">'
        '<div style="background:#d32f2f;border-radius:12px;padding:24px 28px;margin-bottom:16px;">'
        '<h1 style="margin:0;font-size:20px;color:#fff;">⚠ Cost Threshold Alert</h1>'
        f'<div style="color:#ffcdd2;font-size:13px;margin-top:4px;">{today.isoformat()}</div>'
        '</div>'
        '<div style="background:#fff;border-radius:10px;padding:20px;margin-bottom:16px;">'
        f'<p style="font-size:15px;margin:0 0 12px;">Monthly gross cost has exceeded '
        f'<strong>{currency(threshold, unit)}</strong></p>'
        '<table role="presentation" style="width:100%;font-size:14px;">'
        f'<tr><td style="padding:8px 0;color:#666;">Gross MTD</td>'
        f'<td style="padding:8px 0;text-align:right;font-weight:600;">{currency(gross, unit)}</td></tr>'
        f'<tr><td style="padding:8px 0;color:#666;">Credits Applied</td>'
        f'<td style="padding:8px 0;text-align:right;color:#2e7d32;">-{currency(credits_used, unit)}</td></tr>'
        f'<tr style="border-top:2px solid #eee;"><td style="padding:8px 0;font-weight:600;">Net Cost</td>'
        f'<td style="padding:8px 0;text-align:right;font-weight:700;color:#d32f2f;">{currency(net, unit)}</td></tr>'
        f'<tr><td style="padding:8px 0;color:#666;">Threshold</td>'
        f'<td style="padding:8px 0;text-align:right;">{currency(threshold, unit)}</td></tr>'
        '</table></div>'
        '<div style="text-align:center;font-size:11px;color:#999;padding:12px 0;">'
        'AWS Cost Alerts — Ad-hoc Monitor</div>'
        '</div></body></html>'
    )
