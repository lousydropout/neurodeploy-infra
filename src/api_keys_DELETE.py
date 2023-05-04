import os
import json
from uuid import UUID
from hashlib import sha256
from helpers import cors, dynamodb as ddb, validation
from helpers.logging import logger
import boto3

_PREFIX = os.environ["prefix"]
MODELS_TABLE_NAME = f"{_PREFIX}_Models"

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")


def get_sk(username: str, hashed_value: str) -> str:
    statement = f"SELECT sk FROM {MODELS_TABLE_NAME} WHERE pk='username|{username}' AND BEGINS_WITH(sk, '{hashed_value}');"
    response = dynamodb_client.execute_statement(Statement=statement)
    results = [ddb.from_(x) for x in response.get("Items", [])]
    logger.debug("get_sk results: %s", json.dumps(results, default=str))

    return next(result["sk"] for result in results)


def delete_api_key(username: str, api_key: str, is_hashed: bool) -> dict:
    hashed_value = api_key if is_hashed else sha256(api_key.encode()).hexdigest()
    logger.debug("hashed_value: %s", hashed_value)

    # get the sort key (sk = f'{hashed_value}|{model_name}')
    try:
        sk = get_sk(username=username, hashed_value=hashed_value)
    except:
        return cors.get_response(
            status_code=400,
            body={"error": "The API key with you provided does not exist."},
            methods="DELETE",
        )

    statement = (
        f"DELETE FROM {MODELS_TABLE_NAME} WHERE pk='username|{username}' AND sk='{sk}';"
    )
    response = dynamodb_client.execute_statement(Statement=statement)
    logger.info("deletion response: %s", json.dumps(response, default=str))

    if response.get("ResponseMetadata", {}).get("HTTPStatusCode", -1) == 200:
        return cors.get_response(
            status_code=200,
            body={"message": f"Successfully deleted API key '{api_key}'."},
            methods="DELETE",
        )

    return cors.get_response(
        status_code=500,
        body={"error": f"Unable to delete API key '{api_key}'."},
        methods="DELETE",
    )


def is_hashed(x: str) -> bool:
    try:
        UUID(x)
        logger.debug("%s is not hashed", x)
        return False
    except:
        logger.debug("%s is hashed", x)
        return True


@validation.check_authorization
def handler(event: dict, context):
    username = event["username"]
    api_key = event["path_params"]["api_key"]

    return delete_api_key(
        username=username,
        api_key=api_key,
        is_hashed=is_hashed(api_key),
    )
