import os
import json
from helpers import cors, dynamodb as ddb, validation
from helpers.logging import logger
import boto3

PREFIX = os.environ["prefix"]

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
_CREDS_TABLE_NAME = f"{PREFIX}_Creds"


def get_creds(username: str) -> list[dict]:
    statement = f"SELECT sk, access_key, description, expiration FROM {_CREDS_TABLE_NAME} WHERE pk='username|{username}';"
    response = dynamodb_client.execute_statement(Statement=statement)
    return [ddb.from_(x) for x in response.get("Items", [])]


@validation.check_authorization
def handler(event: dict, context):
    logger.debug("Event: %s", json.dumps(event))
    username = event["username"]
    response = get_creds(username)
    creds = [{"credentials_name": item.pop("sk"), **item} for item in response]

    logger.debug("creds: %s", json.dumps(creds))
    return cors.get_response(
        body={"creds": creds},
        status_code=200,
        methods="GET",
    )
