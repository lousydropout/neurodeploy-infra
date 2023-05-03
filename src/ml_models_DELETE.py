import os
from datetime import datetime
import json
from helpers import cors, validation, dynamodb as ddb
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
    try:
        MODELS_TABLE.put_item(Item=record)
    except Exception as err:
        return (False, str(err))
    return (True, "")


@validation.check_authorization
def handler(event: dict, context):
    username = event["username"]
    model_name = event["path_params"]["model_name"]

    # Delete resource
    try:
        delete_model(username, model_name)
    except Exception as err:
        print(err)
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
