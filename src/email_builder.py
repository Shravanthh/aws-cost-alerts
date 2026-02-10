"""Email building and sending via SES."""

import logging
from decimal import Decimal

import boto3
from formatters import (
    credit_estimate_html,
    credit_estimate_text,
    currency,
    percentage,
    service_table_html,
    service_table_text,
    summary_card,
    summary_row,
    trend_chart_html,
    trend_text,
    wow_card_html,
    wow_text,
)

logger = logging.getLogger(__name__)

_ses = boto3.client("ses")


def _build_alerts_html(alerts):
    if not alerts:
        return ""
    items = []
    for a in alerts:
        if a["type"] == "BUDGET_THRESHOLD":
            items.append(
                f"<li>Budget at {percentage(a['percent_used'])} "
                f"(threshold {percentage(a['threshold_percent'])})</li>"
            )
        elif a["type"] == "DAILY_ANOMALY":
            items.append(
                f"<li>Daily anomaly: {percentage(a['percent_over_average'])} above average</li>"
            )
    if not items:
        return ""
    return (
        '<div style="background:#fff3f3;border-left:4px solid #d32f2f;border-radius:8px;'
        'padding:14px 18px;margin-bottom:16px;">'
        '<div style="font-weight:600;color:#d32f2f;font-size:13px;margin-bottom:6px;">⚠ Alerts</div>'
        f'<ul style="padding-left:16px;margin:0;color:#b71c1c;font-size:13px;">{"".join(items)}</ul>'
        "</div>"
    )


def _build_alerts_text(alerts):
    if not alerts:
        return ""
    lines = ["Alerts:"]
    for a in alerts:
        if a["type"] == "BUDGET_THRESHOLD":
            lines.append(f"- Budget at {percentage(a['percent_used'])} (threshold {percentage(a['threshold_percent'])})")
        elif a["type"] == "DAILY_ANOMALY":
            lines.append(f"- Daily anomaly: {percentage(a['percent_over_average'])} above average")
    return "\n".join(lines)


def _compute_credit_summary(mtd, forecast, credit_info):
    """Derive credit-related display values."""
    cu = credit_info.get("credits_used", Decimal("0")) if credit_info else Decimal("0")
    unit = credit_info.get("unit", "USD") if credit_info else "USD"
    mtd_amt = mtd.get("amount", Decimal("0")) if mtd else Decimal("0")
    fc_amt = forecast.get("amount") if forecast else None

    credits_str = currency(cu, unit)
    net_str = currency(mtd_amt - cu, unit)

    if fc_amt is not None:
        total_end = mtd_amt + fc_amt
        month_end_str = currency(total_end, unit)
        end_after_credits_str = currency(total_end - cu, unit)
    else:
        month_end_str = "N/A"
        end_after_credits_str = "N/A"

    return credits_str, net_str, month_end_str, end_after_credits_str


def build_email(report_date, data, cfg):
    """Build subject, HTML body, and text body for the cost report email."""
    mtd = data["month_to_date"]
    forecast = data["forecast"]
    prev = data["previous_day"]
    daily = data["daily_costs"]
    breakdown = data["service_breakdown"]
    alerts = data["alerts"]
    credit_info = data["credit_info"]
    wow = data.get("week_over_week")
    credit_est = data.get("credit_estimate")

    subject = f"{cfg['subject_prefix']} - {report_date.isoformat()}"

    mtd_str = currency(mtd.get("amount"), mtd.get("unit")) if mtd else "N/A"
    prev_str = currency(prev.get("amount"), prev.get("unit")) if prev else "N/A"
    credits_str, net_str, month_end_str, end_after_str = _compute_credit_summary(mtd, forecast, credit_info)

    alert_html = _build_alerts_html(alerts)
    alert_text = _build_alerts_text(alerts)

    html = (
        '<html><body style="font-family:-apple-system,Arial,sans-serif;color:#1a1a1a;'
        'background:#f0f2f5;margin:0;padding:0;">'
        '<div style="max-width:640px;margin:0 auto;padding:16px;">'
        # Header
        '<div style="background:linear-gradient(135deg,#1a237e,#283593);border-radius:12px;'
        'padding:20px 24px;margin-bottom:16px;">'
        f'<h1 style="margin:0;font-size:20px;color:#fff;font-weight:600;">AWS Cost Report</h1>'
        f'<div style="color:#b3c5ff;font-size:13px;margin-top:4px;">{report_date.isoformat()}</div>'
        "</div>"
        f"{alert_html}"
        # Summary cards — stacked
        '<div style="background:#fff;border-radius:10px;padding:16px;margin-bottom:16px;">'
        '<h2 style="margin:0 0 10px;font-size:15px;color:#333;">Summary</h2>'
        + summary_row([
            ("Month-to-date", mtd_str, "#111"),
            ("Yesterday", prev_str, "#111"),
            ("Forecast Month-end", month_end_str, "#111"),
        ])
        + '</div>'
        # Credits — stacked
        '<div style="background:#fff;border-radius:10px;padding:16px;margin-bottom:16px;">'
        '<h2 style="margin:0 0 10px;font-size:15px;color:#333;">Credits</h2>'
        + summary_row([
            ("Credits Applied", f"-{credits_str}", "#2e7d32"),
            ("Net After Credits", net_str, "#111"),
            ("Month-end After Credits", end_after_str, "#1565c0"),
        ])
        + '</div>'
        # Week over week
        f"{wow_card_html(wow)}"
        # Credit estimate
        f"{credit_estimate_html(credit_est)}"
        # Trend
        '<div style="background:#fff;border-radius:10px;padding:16px;margin-bottom:16px;">'
        '<h2 style="margin:0 0 12px;font-size:15px;color:#333;">Daily Trend</h2>'
        f"{trend_chart_html(daily)}"
        "</div>"
        # Services
        '<div style="background:#fff;border-radius:10px;padding:16px;margin-bottom:16px;">'
        '<h2 style="margin:0 0 12px;font-size:15px;color:#333;">Top Services</h2>'
        f"{service_table_html(breakdown)}"
        "</div>"
        '<div style="text-align:center;font-size:11px;color:#999;padding:12px 0;">'
        "Generated by AWS Cost Alerts</div>"
        "</div></body></html>"
    )

    parts = [f"AWS Cost Report - {report_date.isoformat()}", ""]
    if alert_text:
        parts.extend([alert_text, ""])
    parts.extend([
        f"Month-to-date: {mtd_str}",
        f"Yesterday: {prev_str}",
        f"Forecast month-end: {month_end_str}",
        f"Credits applied: -{credits_str}",
        f"Net after credits: {net_str}",
        f"Forecast month-end after credits: {end_after_str}",
        "",
        wow_text(wow),
        "",
        credit_estimate_text(credit_est),
        "",
        trend_text(daily),
        "",
        service_table_text(breakdown),
    ])
    text = "\n".join(parts)

    return {"subject": subject, "html": html, "text": text}


def send(subject, html, text, sender, recipients):
    """Send email via SES. Returns message ID."""
    if not sender:
        raise ValueError("SENDER_EMAIL is not configured.")
    if not recipients:
        raise ValueError("RECIPIENT_EMAILS is not configured.")
    resp = _ses.send_email(
        Source=sender,
        Destination={"ToAddresses": recipients},
        Message={
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": text, "Charset": "UTF-8"},
                "Html": {"Data": html, "Charset": "UTF-8"},
            },
        },
    )
    return resp.get("MessageId")
