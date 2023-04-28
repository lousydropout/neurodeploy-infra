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


def get_api_keys_info(username: str, model_name: str) -> dict:
    statement = f"SELECT * FROM {MODELS_TABLE_NAME} WHERE pk='username|{username}' AND sk >= '{model_name}|';"
    response = dynamodb_client.execute_statement(Statement=statement)
    results = [ddb.from_(x) for x in response.get("Items", [])]

    for result in results:
        _, api_key = result.pop("sk").split("|")
        result["api_key"] = api_key
    return results


@validation.check_authorization
def handler(event: dict, context):
    username = event["username"]
    path_params = event["path_params"]
    model_name = path_params["model_name"]

    return cors.get_response(
        status_code=200,
        body=get_api_keys_info(username=username, model_name=model_name),
        methods="GET",
    )
