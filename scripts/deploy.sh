#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$REPO_ROOT/.env"
  set +a
fi

STACK_NAME="${STACK_NAME:-aws-cost-alerts}"
AWS_REGION="${AWS_REGION:-}"
AWS_PROFILE="${AWS_PROFILE:-}"
PROJECT_NAME="${PROJECT_NAME:-aws-cost-alerts}"
SAM_ARTIFACT_BUCKET="${SAM_ARTIFACT_BUCKET:-}"
SCHEDULE_EXPRESSION="${SCHEDULE_EXPRESSION:-cron(0 8 * * ? *)}"
SENDER_EMAIL="${SENDER_EMAIL:-}"
RECIPIENT_EMAILS="${RECIPIENT_EMAILS:-}"
EMAIL_SUBJECT_PREFIX="${EMAIL_SUBJECT_PREFIX:-AWS Cost Alert}"
BUDGET_PARAMETER_NAME="${BUDGET_PARAMETER_NAME:-/aws-cost-alerts/budget-amount}"
ARCHIVE_ENABLED="${ARCHIVE_ENABLED:-true}"
ARCHIVE_RETENTION_DAYS="${ARCHIVE_RETENTION_DAYS:-30}"
TOP_SERVICES_COUNT="${TOP_SERVICES_COUNT:-10}"
TREND_DAYS="${TREND_DAYS:-7}"
ANOMALY_THRESHOLD_PERCENT="${ANOMALY_THRESHOLD_PERCENT:-30}"
BUDGET_THRESHOLDS="${BUDGET_THRESHOLDS:-50,75,90,100}"

if [ -z "$SENDER_EMAIL" ]; then
  echo "SENDER_EMAIL is required."
  exit 1
fi

if [ -z "$RECIPIENT_EMAILS" ]; then
  echo "RECIPIENT_EMAILS is required."
  exit 1
fi

aws_args=()
if [ -n "$AWS_REGION" ]; then
  aws_args+=(--region "$AWS_REGION")
fi

if [ -n "$AWS_PROFILE" ]; then
  aws_args+=(--profile "$AWS_PROFILE")
fi

if [ -z "$SAM_ARTIFACT_BUCKET" ]; then
  if [ -z "$AWS_REGION" ]; then
    echo "AWS_REGION is required to auto-generate SAM_ARTIFACT_BUCKET."
    exit 1
  fi
  account_id="$(aws "${aws_args[@]}" sts get-caller-identity --query Account --output text)"
  safe_project_name="$(echo "$PROJECT_NAME" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9-' '-')"
  SAM_ARTIFACT_BUCKET="${safe_project_name}-sam-artifacts-${account_id}-${AWS_REGION}"
fi

if ! aws "${aws_args[@]}" s3api head-bucket --bucket "$SAM_ARTIFACT_BUCKET" >/dev/null 2>&1; then
  echo "Creating SAM artifacts bucket: $SAM_ARTIFACT_BUCKET"
  aws "${aws_args[@]}" s3 mb "s3://${SAM_ARTIFACT_BUCKET}"
fi

sam build

deploy_args=(
  deploy
  --stack-name "$STACK_NAME"
  --capabilities CAPABILITY_IAM
  --s3-bucket "$SAM_ARTIFACT_BUCKET"
  --no-confirm-changeset
  --no-fail-on-empty-changeset
)

if [ -n "$AWS_REGION" ]; then
  deploy_args+=(--region "$AWS_REGION")
fi

if [ -n "$AWS_PROFILE" ]; then
  deploy_args+=(--profile "$AWS_PROFILE")
fi

parameter_overrides=(
  "ProjectName=$PROJECT_NAME"
  "ScheduleExpression=$SCHEDULE_EXPRESSION"
  "SenderEmail=$SENDER_EMAIL"
  "RecipientEmails=$RECIPIENT_EMAILS"
  "EmailSubjectPrefix=$EMAIL_SUBJECT_PREFIX"
  "BudgetParameterName=$BUDGET_PARAMETER_NAME"
  "ArchiveEnabled=$ARCHIVE_ENABLED"
  "ArchiveRetentionDays=$ARCHIVE_RETENTION_DAYS"
  "TopServicesCount=$TOP_SERVICES_COUNT"
  "TrendDays=$TREND_DAYS"
  "AnomalyThresholdPercent=$ANOMALY_THRESHOLD_PERCENT"
  "BudgetThresholds=$BUDGET_THRESHOLDS"
)

deploy_args+=(--parameter-overrides "${parameter_overrides[@]}")

sam "${deploy_args[@]}"
