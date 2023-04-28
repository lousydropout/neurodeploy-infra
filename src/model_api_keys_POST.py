import os
from uuid import uuid4 as uuid
from datetime import datetime
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


def insert_api_key_record(username: str, model_name: str):
    api_key = str(uuid())
    record = {
        "pk": f"username|{username}",
        "sk": f"{model_name}|{api_key}",
        "api_key": api_key,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    MODELS_TABLE.put_item(Item=record)


@validation.check_authorization
def handler(event: dict, context):
    username = event["username"]
    path_params = event["path_params"]
    model_name = path_params["model_name"]

    return cors.get_response(
        status_code=200,
        body=insert_api_key_record(username=username, model_name=model_name),
        methods="GET",
    )
