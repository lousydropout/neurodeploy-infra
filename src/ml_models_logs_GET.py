import os
from datetime import datetime
import json
from helpers import cors, validation, dynamodb as ddb
from helpers.logging import logger
import boto3

_PREFIX = os.environ["prefix"]
_REGION = os.environ["region_name"]
USAGES_TABLE_NAME = f"{_PREFIX}_Usages"
LOGS_BUCKET_NAME = f"{_PREFIX}-logs-{_REGION}"

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
s3 = boto3.client("s3")


def get_link(object_name: str, expiration: int = 60) -> str:
    # check if object exists
    _ = s3.get_object(Bucket=LOGS_BUCKET_NAME, Key=object_name)

    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": LOGS_BUCKET_NAME, "Key": object_name},
        ExpiresIn=expiration,
    )


def get_log_info(
    username: str,
    model_name: str,
    timestamp: str | None,
) -> tuple[bool, dict]:
    statement = " ".join(
        [
            'SELECT "status_code", "location", "duration", "input", "output", "error"',
            f"FROM {USAGES_TABLE_NAME}",
            f"WHERE pk='{username}|{model_name}'",
            f"AND sk='{timestamp}'",
        ]
    )
    logger.debug("statement: %s", statement)
    response = dynamodb_client.execute_statement(Statement=statement, Limit=1)
    items = [ddb.from_(x) for x in (response.get("Items") or [{}])]
    if len(items) == 1:
        item = items[0]
    else:
        logger.error("items: ", items)
        return False, {
            "status_code": 404,
            "method": "GET",
            "body": {"error": "No logs for the provided timestamp was found."},
        }

    try:
        link = get_link(object_name=item["location"])
    except Exception as err:
        logger.exception(err)
        return False, {
            "status_code": 500,
            "method": "GET",
            "body": {
                "error": "Something went wrong when retrieving the download link."
            },
        }

    try:
        result = {
            "status_code": int(item["status_code"]),
            "location": link,
            "duration": int(item["duration"]),
            "input": item["input"],
            "output": item["output"],
            "error": item["error"],
        }
    except Exception as err:
        logger.exception(err)
        return False, {
            "status_code": 500,
            "method": "GET",
            "body": {
                "error": "Something went wrong."
                " Please let us know about our screw-up (and provided as much info as you can) at 'support@neurodeploy.com'."
            },
        }

    return True, result


@validation.check_authorization
def handler(event: dict, context):
    # get params
    username = event["username"]
    model_name = event["path_params"]["model_name"]
    ts = event["path_params"]["log_timestamp"]

    # validate timestamp
    try:
        timestamp = ts if datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%f") else None
    except:
        return cors.get_response(
            status_code=404,
            body={"error": "The requested resource does not exist"},
            methods="GET",
        )

    # get log
    succcess, log_info = get_log_info(
        username=username,
        model_name=model_name,
        timestamp=timestamp,
    )
    if not succcess:
        return cors.get_response(**log_info)
    logger.debug("log_info: %s", json.dumps(log_info, default=str))

    return cors.get_response(
        status_code=200,
        body=log_info,
        methods="GET",
    )
