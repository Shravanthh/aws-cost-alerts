# AWS Cost Alerts

Automated weekly AWS cost reports delivered to your inbox via SES. Built with AWS SAM.

## What You Get

**Weekly Report Email** (every Saturday, 8:00 AM UTC) with:
- Month-to-date spend and forecast month-end
- Most recent day cost
- Credits applied, net after credits, forecast after credits
- Week-over-week comparison
- Credit burn rate and projected monthly usage
- 7-day daily trend chart
- Top 10 services breakdown
- Budget threshold and daily anomaly alerts

## Architecture

```
EventBridge (Saturday 8 AM UTC)  ──▶  CostAlertFunction  ──▶  SES (report email)
                                             │                       │
                                             ▼                       ▼
                                       Cost Explorer           S3 (archive)
```

### Module Structure

```
src/
├── handler.py        # Lambda orchestrator
├── config.py         # Environment config loading
├── cost_explorer.py  # Cost Explorer API queries (4 calls per run)
├── alerts.py         # Budget threshold + anomaly detection
├── formatters.py     # Currency, HTML components, charts
├── email_builder.py  # Email assembly + SES sending
└── archive.py        # S3 report archival
```

## Prerequisites

- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured with credentials
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- SES sender email verified in the target AWS region
- Python 3.14 runtime (used by Lambda)

## Quick Start

1. Clone the repo:
```bash
git clone https://github.com/Shravanthh/aws-cost-alerts.git
cd aws-cost-alerts
```

2. Copy and configure environment:
```bash
cp .env.example .env
# Edit .env with your values
```

3. Deploy:
```bash
./scripts/deploy.sh
```

That's it. You'll receive your first cost report the coming Saturday at 8:00 AM UTC.

## Configuration

All configuration is via the `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `STACK_NAME` | `aws-cost-alerts` | CloudFormation stack name |
| `AWS_REGION` | — | AWS region to deploy to (required) |
| `AWS_PROFILE` | — | AWS CLI profile name |
| `SENDER_EMAIL` | — | SES-verified sender email (required) |
| `RECIPIENT_EMAILS` | — | Comma-separated recipient emails (required) |
| `EMAIL_SUBJECT_PREFIX` | `AWS Cost Alert` | Email subject prefix |
| `SCHEDULE_EXPRESSION` | `cron(0 8 ? * 7 *)` | Report schedule ([EventBridge cron](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-cron-expressions.html)) |
| `BUDGET_AMOUNT` | `10` | Monthly budget in USD for threshold alerts |
| `ARCHIVE_ENABLED` | `true` | Archive reports to S3 |
| `ARCHIVE_RETENTION_DAYS` | `30` | Days to retain archived reports |
| `TOP_SERVICES_COUNT` | `10` | Number of top services in breakdown |
| `TREND_DAYS` | `7` | Days in the daily trend chart |
| `ANOMALY_THRESHOLD_PERCENT` | `30` | % above average to flag as anomaly |
| `BUDGET_THRESHOLDS` | `50,75,90,100` | Budget % thresholds to trigger alerts |

## SES Setup

If your SES is in **sandbox mode** (default for new accounts), you must verify both sender and recipient emails:

```bash
aws ses verify-email-identity --email-address sender@example.com --region us-east-1
aws ses verify-email-identity --email-address recipient@example.com --region us-east-1
```

Each address will receive a verification link. Click it to verify.

For production use, [request SES production access](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html) to send to any recipient.

## How Costs Are Calculated

| Metric | Calculation |
|--------|-------------|
| **Month-to-date** | `GetCostAndUsage` for current month, excluding Credit/Refund/EDP record types |
| **Forecast month-end** | MTD + `GetCostForecast` (remaining days from tomorrow) |
| **Credits applied** | `GetCostAndUsage` filtered to Credit + EDP record types only |
| **Net after credits** | MTD − Credits |
| **Week-over-week** | This week (Mon–today) vs same days last week, derived from the same API call |
| **Credit burn rate** | Average daily credit usage over last 14 days |

## What Gets Deployed

| Resource | Type | Purpose |
|----------|------|---------|
| `CostAlertFunction` | Lambda (128 MB) | Weekly cost report |
| `DailyLogGroup` | CloudWatch Logs | 14-day retention |
| `ArchiveBucket` | S3 (conditional) | Report JSON archive |
| EventBridge Rule | Schedule | Saturday 8 AM UTC trigger |
| IAM Role | Per function | Least-privilege policies |

### IAM Permissions (Least Privilege)

- `ce:GetCostAndUsage`, `ce:GetCostForecast` — Cost Explorer (requires `Resource: *`)
- `ses:SendEmail` — scoped to account SES identities
- `s3:PutObject` — scoped to archive bucket (conditional)

## Manual Testing

```bash
aws lambda invoke \
  --function-name aws-cost-alerts-daily \
  --payload '{}' \
  --region us-east-1 \
  /tmp/output.json && cat /tmp/output.json | python3 -m json.tool && rm /tmp/output.json
```

## Customization

**Change schedule**: Update `SCHEDULE_EXPRESSION` in `.env` and redeploy. Uses [EventBridge cron syntax](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-cron-expressions.html).

**Change budget**: Update `BUDGET_AMOUNT` in `.env` and redeploy.

**Disable archiving**: Set `ARCHIVE_ENABLED=false` in `.env`.

**Change cost metric**: Set `COST_METRIC` in `.env` to `BlendedCost`, `AmortizedCost`, etc.

## Cleanup

```bash
aws cloudformation delete-stack --stack-name aws-cost-alerts
```

Note: The S3 archive bucket has `DeletionPolicy: Retain` and won't be deleted with the stack. Delete it manually if needed.

## License

MIT
