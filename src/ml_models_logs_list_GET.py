import os
from datetime import datetime
import json
from helpers import cors, validation, dynamodb as ddb
from helpers.logging import logger
import boto3

_PREFIX = os.environ["prefix"]
USAGES_TABLE_NAME = f"{_PREFIX}_Usages"

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")


def get_logs_info(
    username: str,
    model_name: str,
    limit: int,
    asc: bool,
    start_from: str | None,
    next_token: str | None,
    inclusive: bool,
) -> dict:
    fields = ["sk", "status_code", "duration", "input", "output", "error"]
    field_string = ", ".join([f'"{x}"' for x in fields])  # wrap fields in double quotes
    sort_clause = ""
    if asc and start_from:
        sort_clause = (
            f"AND sk >= '{start_from}'" if inclusive else f"AND sk > '{start_from}'"
        )
    elif (not asc) and start_from:
        sort_clause = (
            f"AND sk <= '{start_from}'" if inclusive else f"AND sk < '{start_from}'"
        )
    statement = " ".join(
        [
            f"SELECT {field_string}",
            f"FROM {USAGES_TABLE_NAME}",
            f"WHERE pk='{username}|{model_name}'",
            sort_clause,
            f"ORDER BY sk {'ASC' if asc else 'DESC'};",
        ]
    )
    logger.debug("statement: %s", statement)
    if next_token:
        response = dynamodb_client.execute_statement(
            Statement=statement, NextToken=next_token
        )
    else:
        response = dynamodb_client.execute_statement(Statement=statement, Limit=limit)
    logger.debug("response: %s", json.dumps(response, default=str))

    # parse results
    results = [ddb.from_(x) for x in response.get("Items", [])]
    keys = [
        {
            "timestamp": result["sk"],
            "status_code": int(result["status_code"]),
            "duration": int(result["duration"]),
            "input": result["input"],
            "output": result["output"],
            "error": result["error"],
        }
        for result in results
    ]

    # get next token if present
    next = response["NextToken"] if "NextToken" in response else None

    return {"logs": keys, "next_token": next}


@validation.check_authorization
def handler(event: dict, context):
    params = event["params"]

    # get username
    username = event["username"]

    # get model name
    model_name = event["path_params"]["model_name"]

    # get limit
    try:
        val = int(params.get("limit"))
        limit = val if val < 100 and val > 0 else 10
    except:
        limit = 10

    # is ascending or descending (default to ascending)
    try:
        asc = params.get("sort-by")[:4].lower() != "desc"
    except:
        asc = True

    # get starting point (default to None)
    try:
        _ = params.get("start-from")
        start_from = _ if datetime.strptime(_, "%Y-%m-%dT%H:%M:%S.%f") else None
    except:
        start_from = None

    # get inclusivity (default to True)
    try:
        inclusive = (params.get("inclusive") or "").lower() != "false"
    except:
        inclusive = True

    # get next token
    next_token = params.get("next-token")

    logs = get_logs_info(
        username=username,
        model_name=model_name,
        limit=limit,
        asc=asc,
        start_from=start_from,
        next_token=next_token,
        inclusive=inclusive,
    )
    logger.debug("logs: %s", json.dumps(logs, default=str))

    return cors.get_response(
        status_code=200,
        body=logs,
        methods="GET",
    )
