import os
from uuid import uuid4 as uuid
from datetime import datetime, timedelta
import time
from hashlib import sha256
from helpers import cors
from helpers.validation import check_authorization, get_param
import boto3

_PREFIX = os.environ["prefix"]
_REGION_NAME = os.environ["region_name"]
MODELS_S3_BUCKET = f"{_PREFIX}-models-{_REGION_NAME}"

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
MODELS_TABLE_NAME = f"{_PREFIX}_Models"
MODELS_TABLE = dynamodb.Table(MODELS_TABLE_NAME)


def insert_api_key_record(
    username: str, model_name: str, description: str, expiration
) -> dict:
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
    # set expiration
    exp = None
    if expiration:
        exp = datetime.utcnow() + timedelta(minutes=exp)
        record.update(
            {
                "ttl": int(time.mktime(exp.timetuple())),
                "expires_at": exp.isoformat(),
            }
        )

    MODELS_TABLE.put_item(Item=record)

    return {"api-key": api_key}


@check_authorization
def handler(event: dict, context):
    username = event["username"]

    # model-name or model_name
    model_name = get_param("model-name", event)
    if not model_name:
        model_name = get_param("model_name", event, "*")

    # description
    description = get_param("description", event, "")

    # expiration
    expiration: str = get_param("expiration", event)
    if expiration.isdecimal():
        expiration = int(expiration)
    else
        expiration = None

    return cors.get_response(
        status_code=200,
        body=insert_api_key_record(
            username=username,
            model_name=model_name,
            description=description,
            expiration=expiration,
        ),
        methods="POST",
    )
