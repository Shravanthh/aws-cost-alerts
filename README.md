# AWS Cost Alerts (SAM)

This project deploys a daily AWS Cost Alert system using AWS SAM. It queries Cost Explorer, builds a daily report (HTML + text), sends it via SES, and optionally archives the report JSON to S3.

## Prerequisites

- AWS CLI configured with credentials
- SAM CLI installed
- SES sender email verified in the target AWS region

## Deploy

1. Build the SAM application:

```bash
sam build
```

2. Deploy with guided setup (first time):

```bash
sam deploy --guided
```

3. Example deploy with parameter overrides:

```bash
sam deploy \
  --stack-name aws-cost-alerts \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    ProjectName=aws-cost-alerts \
    SenderEmail=verified-sender@example.com \
    RecipientEmails=recipient1@example.com,recipient2@example.com \
    EmailSubjectPrefix="AWS Cost Alert" \
    BudgetParameterName=/aws-cost-alerts/budget-amount \
    ArchiveEnabled=true \
    ArchiveRetentionDays=30 \
    TopServicesCount=10 \
    TrendDays=7 \
    AnomalyThresholdPercent=30 \
    BudgetThresholds=50,75,90,100
```

## Notes

- The stack creates an SSM parameter (default `/aws-cost-alerts/budget-amount`) with value `10`.
- SES must be verified in the region you deploy to.
- The report runs daily at `08:00 UTC` by default (see `ScheduleExpression` in `template.yaml`).
