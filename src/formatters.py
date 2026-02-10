"""Formatting helpers for currency, percentages, and HTML components.
All HTML is designed for Gmail mobile compatibility (no media queries, no CSS classes)."""

from decimal import Decimal, InvalidOperation
from html import escape


def currency(amount, unit):
    if amount is None:
        return "N/A"
    if unit == "USD":
        return f"${amount:.2f}"
    return f"{amount:.2f} {unit}" if unit else f"{amount:.2f}"


def percentage(value):
    if value is None:
        return "N/A"
    return f"{value:.1f}%"


def _clamp_percent(value):
    try:
        p = float(value) if value is not None else 0.0
    except (TypeError, ValueError, InvalidOperation):
        return 0.0
    return max(0.0, min(100.0, p))


def percent_bar(value, color="#4f8ef7"):
    w = f"{_clamp_percent(value):.1f}%"
    return (
        f'<div style="background:#eef1f5;border-radius:6px;overflow:hidden;height:8px;">'
        f'<div style="background:{color};width:{w};height:8px;border-radius:6px;"></div>'
        "</div>"
    )


def summary_card(label, value, color="#111"):
    """Single stacked card — full width, mobile safe."""
    return (
        '<div style="background:#f8f9fb;border-radius:8px;padding:12px 16px;margin-bottom:8px;">'
        f'<div style="font-size:12px;color:#666;margin-bottom:2px;">{label}</div>'
        f'<div style="font-size:20px;font-weight:700;color:{color};">{value}</div>'
        '</div>'
    )


def summary_row(cards):
    """Render a list of (label, value, color) tuples as stacked cards."""
    return "".join(summary_card(l, v, c) for l, v, c in cards)


def service_table_html(breakdown):
    if not breakdown or not breakdown.get("services"):
        return '<p style="color:#888;">No service data available.</p>'

    rows = []
    for i, s in enumerate(breakdown["services"]):
        name = escape(s.get("service", "Unknown"))
        amt = currency(s.get("amount"), s.get("unit"))
        pct = percentage(s.get("percent_of_total"))
        bg = "#f8f9fb" if i % 2 == 0 else "#fff"
        # Each service as a compact row: name on top, cost + percent below
        rows.append(
            f'<div style="background:{bg};padding:10px 12px;border-bottom:1px solid #eee;">'
            f'<div style="font-size:13px;margin-bottom:4px;">{name}</div>'
            f'<div style="display:inline-block;font-size:14px;font-weight:600;">{amt}</div>'
            f'<div style="display:inline-block;font-size:12px;color:#888;margin-left:8px;">{pct}</div>'
            f'<div style="margin-top:6px;">{percent_bar(s.get("percent_of_total"))}</div>'
            '</div>'
        )

    return "".join(rows)


def service_table_text(breakdown):
    if not breakdown or not breakdown.get("services"):
        return "No service data available."
    lines = ["Service Breakdown:"]
    for s in breakdown["services"]:
        lines.append(
            f"- {s.get('service', 'Unknown')}: "
            f"{currency(s.get('amount'), s.get('unit'))} "
            f"({percentage(s.get('percent_of_total'))})"
        )
    return "\n".join(lines)


def trend_chart_html(daily_costs):
    if not daily_costs:
        return '<p style="color:#888;">No daily trend data available.</p>'

    max_amt = max((e["amount"] for e in daily_costs), default=Decimal("0"))
    col_pct = f"{100 / len(daily_costs):.1f}%"
    bars = []
    for e in daily_costs:
        amt = e.get("amount", Decimal("0"))
        label = e.get("date", "")[-5:] if e.get("date") else ""
        h = int((amt / max_amt) * 70) if max_amt > 0 else 0
        if amt > 0 and h < 3:
            h = 3
        bars.append(
            f'<td style="vertical-align:bottom;text-align:center;width:{col_pct};padding:0 1px;">'
            f'<div style="font-size:9px;color:#666;margin-bottom:2px;overflow:hidden;'
            f'white-space:nowrap;">{currency(amt, e.get("unit", "USD"))}</div>'
            f'<div style="height:{h}px;background:linear-gradient(180deg,#4f8ef7,#2563eb);'
            f'border-radius:3px 3px 0 0;margin:0 auto;max-width:24px;min-width:8px;"></div>'
            f'<div style="font-size:9px;color:#999;margin-top:4px;">{escape(label)}</div>'
            "</td>"
        )

    return (
        '<table role="presentation" style="width:100%;border-collapse:collapse;table-layout:fixed;">'
        f"<tr>{''.join(bars)}</tr></table>"
    )


def wow_card_html(wow):
    if not wow:
        return ""
    unit = wow.get("unit", "USD")
    this_w = currency(wow["this_week"], unit)
    last_w = currency(wow["last_week"], unit)
    pct = wow.get("change_pct")
    if pct is not None:
        arrow = "▲" if pct > 0 else "▼" if pct < 0 else "–"
        color = "#d32f2f" if pct > 0 else "#2e7d32" if pct < 0 else "#666"
        pct_str = f'{arrow} {abs(pct):.1f}%'
    else:
        pct_str = "N/A"
        color = "#666"
    return (
        '<div style="background:#fff;border-radius:10px;padding:16px;margin-bottom:16px;">'
        '<h2 style="margin:0 0 10px;font-size:15px;color:#333;">Week over Week</h2>'
        + summary_row([
            ("This Week", this_w, "#111"),
            ("Last Week (same days)", last_w, "#111"),
            ("Change", pct_str, color),
        ])
        + '</div>'
    )


def wow_text(wow):
    if not wow:
        return ""
    unit = wow.get("unit", "USD")
    pct = wow.get("change_pct")
    pct_str = f"{pct:+.1f}%" if pct is not None else "N/A"
    return (
        f"Week over Week:\n"
        f"- This week: {currency(wow['this_week'], unit)}\n"
        f"- Last week (same days): {currency(wow['last_week'], unit)}\n"
        f"- Change: {pct_str}"
    )


def credit_estimate_html(est):
    if not est:
        return ""
    unit = est.get("unit", "USD")
    daily = currency(est["avg_daily_burn"], unit)
    used = currency(est["credits_used_so_far"], unit)
    projected = currency(est["projected_monthly_credits"], unit)
    days_left = est["days_remaining"]
    return (
        '<div style="background:#fff;border-radius:10px;padding:16px;margin-bottom:16px;">'
        '<h2 style="margin:0 0 10px;font-size:15px;color:#333;">Credit Usage Estimate</h2>'
        + summary_row([
            ("Daily Burn Rate", f"{daily}/day", "#7b1fa2"),
            ("Used This Month", used, "#2e7d32"),
            ("Projected Monthly", projected, "#1565c0"),
        ])
        + f'<div style="font-size:12px;color:#888;margin-top:4px;">'
        f'{days_left} days remaining in billing period</div>'
        '</div>'
    )


def credit_estimate_text(est):
    if not est:
        return ""
    unit = est.get("unit", "USD")
    return (
        f"Credit Usage Estimate:\n"
        f"- Daily burn rate: {currency(est['avg_daily_burn'], unit)}/day\n"
        f"- Used this month: {currency(est['credits_used_so_far'], unit)}\n"
        f"- Projected monthly: {currency(est['projected_monthly_credits'], unit)}\n"
        f"- Days remaining: {est['days_remaining']}"
    )


def trend_text(daily_costs):
    if not daily_costs:
        return "No daily trend data available."
    lines = ["Daily Trend:"]
    for e in daily_costs:
        lines.append(f"- {e.get('date', '')}: {currency(e.get('amount'), e.get('unit'))}")
    return "\n".join(lines)
