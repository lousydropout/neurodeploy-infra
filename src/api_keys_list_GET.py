import os
from helpers import cors, validation, dynamodb as ddb
import boto3

_PREFIX = os.environ["prefix"]
MODELS_TABLE_NAME = f"{_PREFIX}_Models"

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")


def get_api_keys_info(username: str, model_name: str) -> dict:
    statement = f"""SELECT * FROM {MODELS_TABLE_NAME} WHERE pk='username|{username}' AND hashed_key IS NOT MISSING;"""
    response = dynamodb_client.execute_statement(Statement=statement)
    results = [ddb.from_(x) for x in response.get("Items", [])]

    keys = [
        {
            "last8": result["last8"],
            "created_at": result["created_at"],
            "hashed_key": result["hashed_key"],
            "model_name": result["model_name"],
            "description": result.get("description") or "",
        }
        for result in results
        if (result["model_name"] == model_name if model_name else True)
    ]

    return {"api_keys": keys}


@validation.check_authorization
def handler(event: dict, context):
    username = event["username"]
    model_name = event["query_params"].get("model_name")
    if model_name == "*":
        model_name = None

    return cors.get_response(
        status_code=200,
        body=get_api_keys_info(username=username, model_name=model_name),
        methods="GET",
    )
