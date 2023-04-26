import os
from helpers import cors, validation, dynamodb as ddb
import boto3

_PREFIX = os.environ["prefix"]
MODELS_TABLE_NAME = f"{_PREFIX}_Models"


# boto3
dynamodb = boto3.client("dynamodb")


# model_name, model_type, persistence_type, updated_at
def get_models(username: str) -> list[dict]:
    statement = f"SELECT sk, library, filetype, created_at, updated_at FROM {MODELS_TABLE_NAME} WHERE pk='username|{username}';"
    response = dynamodb.execute_statement(Statement=statement)
    results = [ddb.from_(x) for x in response.get("Items", [])]
    for result in results:
        result["model_name"] = result.pop("sk")
    return [result for result in results if not result["deleted"]]


@validation.check_authorization
def handler(event: dict, context):
    try:
        results = get_models(event["username"])
    except Exception as err:
        print("Error: ", err)
        results = []

    return cors.get_response(status_code=200, body={"models": results}, methods="GET")
