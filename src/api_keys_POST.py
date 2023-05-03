import os
from uuid import uuid4 as uuid
from datetime import datetime
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


def insert_api_key_record(username: str, model_name: str, description: str) -> dict:
    api_key = str(uuid())
    hashed_value = sha256(api_key.encode()).hexdigest()

    record = {
        "pk": f"username|{username}",
        "sk": f"{hashed_value}|{model_name}",
        "description": description,
        "hashed_key": hashed_value,
        "model_name": model_name,
        "last8": api_key[-8:],
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    MODELS_TABLE.put_item(Item=record)

    return {"api_key": api_key}


@validation.check_authorization
def handler(event: dict, context):
    username = event["username"]
    model_name = event["query_params"].get("model_name") or "*"
    description = event["query_params"].get("description") or ""

    return cors.get_response(
        status_code=200,
        body=insert_api_key_record(
            username=username, model_name=model_name, description=description
        ),
        methods="POST",
    )
