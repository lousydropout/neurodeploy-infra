import os
from helpers import cors, validation, dynamodb as ddb
import boto3

_PREFIX = os.environ["prefix"]
_REGION_NAME = os.environ["region_name"]
MODELS_S3_BUCKET = f"{_PREFIX}-models-{_REGION_NAME}"

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
MODELS_TABLE_NAME = f"{_PREFIX}_Models"
MODELS_TABLE = dynamodb.Table(MODELS_TABLE_NAME)


def delete_api_key(username: str, model_name: str, api_key: str) -> dict:
    statement = f"DELETE FROM {MODELS_TABLE_NAME} WHERE pk='username|{username}' AND sk='{model_name}|{api_key}';"
    response = dynamodb_client.execute_statement(Statement=statement)

    return response


@validation.check_authorization
def handler(event: dict, context):
    username = event["username"]
    path_params = event["path_params"]
    model_name = path_params["model_name"]
    api_key = path_params["api_key"]

    return cors.get_response(
        status_code=200,
        body=delete_api_key(username=username, model_name=model_name, api_key=api_key),
        methods="GET",
    )
