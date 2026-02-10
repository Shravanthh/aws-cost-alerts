"""S3 archival of daily cost reports."""

import json
import logging

import boto3

logger = logging.getLogger(__name__)

_s3 = boto3.client("s3")


def archive_report(report, report_date, bucket):
    """Write report JSON to S3. Returns the object key."""
    if not bucket:
        logger.warning("ARCHIVE_BUCKET is not configured.")
        return None
    key = f"reports/{report_date.isoformat()}.json"
    _s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(report, indent=2, default=str).encode("utf-8"),
        ContentType="application/json",
    )
    return key
