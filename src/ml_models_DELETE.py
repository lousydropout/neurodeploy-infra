import os
from datetime import datetime
import json
from helpers import cors, validation, dynamodb as ddb
from helpers.logging import logger
from api_keys_list_GET import get_api_keys_info
import boto3

_PREFIX = os.environ["prefix"]
_REGION_NAME = os.environ["region_name"]
MODELS_S3_BUCKET = f"{_PREFIX}-models-{_REGION_NAME}"
LOGS_S3_BUCKET = f"{_PREFIX}-logs-{_REGION_NAME}"

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
MODELS_TABLE_NAME = f"{_PREFIX}_Models"
MODELS_TABLE = dynamodb.Table(MODELS_TABLE_NAME)

# other boto3 clients
apigw = boto3.client("apigateway")
iam = boto3.client("iam")
s3 = boto3.client("s3")


def get_model(username: str, model_name: str) -> dict:
    statement = f"SELECT * FROM {MODELS_TABLE_NAME} WHERE pk='username|{username}' AND sk='{model_name}';"
    response = dynamodb_client.execute_statement(Statement=statement)
    return ddb.from_(response.get("Items", [{}])[0])


def delete_model(username: str, model_name: str) -> tuple[bool, str]:
    try:
        record = get_model(username=username, model_name=model_name)
    except Exception as err:
        return (False, str(err))

    record.update(
        {
            "is_deleted": True,
            "deleted_at": datetime.utcnow().isoformat(),
        }
    )
    logger.debug("new model record 1: %s", json.dumps(record, default=str))
    try:
        MODELS_TABLE.put_item(Item=record)
    except Exception as err:
        logger.exception(err)
        return (False, str(err))

    record = get_model(username=username, model_name=model_name)
    logger.debug("new model record 2: %s", json.dumps(record, default=str))
    return (True, "")


def delete_associated_api_keys(username: str, model_name: str) -> bool:
    keys = get_api_keys_info(username=username, model_name=model_name)
    logger.debug("keys: %s", json.dumps(keys, default=str))
    statement = f"DELETE FROM {MODELS_TABLE_NAME} WHERE pk='username|{username}' AND sk='{{hashed_key}}|{model_name}';"
    statements = [
        {"Statement": statement.format(hashed_key=item["hashed_key"])}
        for item in keys["api-keys"]
    ]

    if not statements:
        return True

    response = dynamodb_client.batch_execute_statement(Statements=statements)
    logger.debug("deletion response: %s", json.dumps(response, default=str))

    errors = [x["Error"] for x in response["Responses"] if "Error" in x]
    if errors:
        logger.error("Deletion errors: %s", json.dumps(errors, default=str))
        return False

    return True


@validation.check_authorization
def handler(event: dict, context):
    username = event["username"]
    model_name = event["path_params"]["model_name"]
    delete_api_keys = (
        event["params"].get("delete_api_keys") or "true"
    ).strip().lower() == "true"

    # 1. delete API keys associated with model
    success = (
        delete_associated_api_keys(username=username, model_name=model_name)
        if delete_api_keys
        else True
    )
    if not success:
        return cors.get_response(
            status_code=500,
            body={
                "error_message": f"An error occurred when deleting the API keys associated with model '{model_name}'. "
                "Please try again later or set the query param 'delete_api_keys' to 'false'."
            },
        )

    # 2. delete model
    success, error = delete_model(username, model_name)
    if not success:
        logger.error(error)
        return cors.get_response(
            status_code=400,
            body={"error_message": f"Failed to delete model {model_name}"},
            methods="DELETE",
        )

    return cors.get_response(
        status_code=200,
        body={"message": f"deleted model {model_name}"},
        methods="DELETE",
    )
