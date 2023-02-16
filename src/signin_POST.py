import os
from typing import Tuple
import json
from hashlib import sha256
import boto3
from boto3.dynamodb.types import TypeSerializer, TypeDeserializer
from helpers.DecimalEncoder import DecimalEncoder

dynamodb = boto3.client("dynamodb")
serializer = TypeSerializer()
deserializer = TypeDeserializer()

UTF_8 = "utf-8"
_USERS_TABLE_NAME = "neurodeploy_Users"
_USERS = os.environ[_USERS_TABLE_NAME]
_SESSIONS = os.environ["neurodeploy_Sessions"]


def is_password_correct(password: str, salt: str, hashed: str) -> bool:
    return sha256((password + salt).encode(UTF_8)).hexdigest() == hashed


def parse(event: dict) -> Tuple[dict, dict]:
    """Return a parsed version of the API Gateway event (with password salted and hashed)."""
    # get body
    body: dict[str, str] = json.loads(event["body"])

    # other stuff
    request_context = event["requestContext"]
    identity = request_context["identity"]

    parsed_event = {
        "http_method": event["httpMethod"],
        "path": event["path"],
        "query_params": event["queryStringParameters"],
        "headers": event["headers"],
        "protocol": request_context["protocol"],
        "domain_name": request_context["domainName"],
        "request_epoch_time": request_context["requestTimeEpoch"],
        "api_id": request_context["apiId"],
        "stage": request_context["stage"],
        "ip_source": identity["sourceIp"],
        "identity": identity,
    }

    return body, parsed_event


def get_user(username: str) -> str:
    response = dynamodb.get_item(
        TableName=_USERS_TABLE_NAME,
        Key={"pk": {"S": f"username::{username}"}},
    )
    items = response.get("Item", {})
    return {k: deserializer.deserialize(v) for k, v in items.items()}


def get_error_response(err: Exception) -> dict:
    return {
        "isBase64Encoded": False,
        "statusCode": 400,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"error": str(err)}),
    }


def handler(event: dict, context):
    # 1. Parse event
    try:
        body, parsed_event = parse(event)
        print(f"Event: {json.dumps(parsed_event)}")
    except Exception as err:
        print(err)
        response = get_error_response(err)
        print("Response: ", json.dumps(response))
        return response

    # 2. Get record
    try:
        user = get_user(body["username"])
        print(f"User: {json.dumps(user, cls=DecimalEncoder)}")
    except Exception as err:
        print(err)
        response = get_error_response(err)
        print("Response: ", json.dumps(response))
        return response

    # 3. Check if the password is correct
    if is_password_correct(
        password=body["password"],
        salt=user["salt"],
        hashed=user["hashed_password"],
    ):
        print(f"Password is correct: True")
    else:
        response = get_error_response("Incorrect password")
        print("Response: ", json.dumps(response))
        return response

    # 4. Create a Session token and write in table

    # 5. Return session token

    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": "logged in",
    }
