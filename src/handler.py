import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    logger.info("Received event: %s", json.dumps(event))

    response = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "archive_enabled": os.getenv("ARCHIVE_ENABLED", "false"),
    }

    return {
        "statusCode": 200,
        "body": json.dumps(response),
    }
