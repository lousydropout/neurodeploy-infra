import os
from hashlib import sha256
from helpers import cors, validation
import boto3

_PREFIX = os.environ["prefix"]
_REGION_NAME = os.environ["region_name"]
MODELS_S3_BUCKET = f"{_PREFIX}-models-{_REGION_NAME}"

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
MODELS_TABLE_NAME = f"{_PREFIX}_Models"
MODELS_TABLE = dynamodb.Table(MODELS_TABLE_NAME)


def delete_api_key(username: str, api_key: str, is_hashed: bool) -> dict:
    hashed_value = api_key if is_hashed else sha256(api_key.encode()).hexdigest()

    statement = f"DELETE FROM {MODELS_TABLE_NAME} WHERE pk='username|{username}' AND sk='{hashed_value}';"
    response = dynamodb_client.execute_statement(Statement=statement)

    return response


@validation.check_authorization
def handler(event: dict, context):
    username = event["username"]
    path_params = event["path_params"]
    api_key = path_params["api_key"]
    is_hashed = event["query_params"].get("is_hashed") or False

    return cors.get_response(
        status_code=200,
        body=delete_api_key(username=username, api_key=api_key, is_hashed=is_hashed),
        methods="DELETE",
    )
