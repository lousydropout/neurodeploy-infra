from typing import Any
import os
import json
from helpers import cors, validation, dynamodb as ddb
from helpers.logging import logger
import boto3

_PREFIX = os.environ["prefix"]
MODELS_TABLE_NAME = f"{_PREFIX}_Models"


# boto3
dynamodb = boto3.client("dynamodb")


def pop(x: dict, key: str, default: str) -> Any:
    try:
        return x.pop(key)
    except KeyError:
        return default


# model_name, model_type, persistence_type, updated_at
def get_models(username: str) -> list[dict]:
    statement = f"SELECT sk, library, filetype, created_at, updated_at, is_deleted, is_public FROM {MODELS_TABLE_NAME} WHERE pk='username|{username}' AND library IS NOT MISSING;"
    response = dynamodb.execute_statement(Statement=statement)
    results = [ddb.from_(x) for x in response.get("Items", [])]
    logger.debug("ml-models: %s", json.dumps(results, default=str))
    for result in results:
        result["model_name"] = result.pop("sk")
    return [result for result in results if not pop(result, "is_deleted", False)]


@validation.check_authorization
def handler(event: dict, context):
    try:
        results = get_models(event["username"])
    except Exception as err:
        logger.exception(err)
        results = []

    return cors.get_response(status_code=200, body={"models": results}, methods="GET")
