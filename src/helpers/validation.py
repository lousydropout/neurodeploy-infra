from typing import Tuple
import os
from datetime import datetime, timedelta
import functools
from hashlib import sha256
import json

from helpers import dynamodb as ddb, secrets

import boto3
import jwt

_ALGO = "HS256"
_BEARER = "Bearer"  # The space at the end of the string is supposed to be there
_REGION: str = os.environ["region_name"]
_JWT_SECRET_NAME = os.environ["jwt_secret"]
_SECRETS: list[str] = secrets.get_secret(_JWT_SECRET_NAME, _REGION)["secrets"]
_USERS_TABLE_NAME = "neurodeploy_Users"
UTF_8 = "utf-8"

dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
_USERS_TABLE = dynamodb.Table(_USERS_TABLE_NAME)


def create_api_token(username: str) -> Tuple[str, datetime]:
    exp = datetime.utcnow() + timedelta(days=1)
    payload = {"username": username, "exp": exp}
    encoded_jwt = jwt.encode(payload, _SECRETS[0], algorithm=_ALGO)
    return encoded_jwt, exp


def validate_jwt(encoded_jwt: str) -> Tuple[bool, dict]:
    valid, payload = False, {}
    for secret in _SECRETS:
        if valid:
            continue
        try:
            payload = jwt.decode(encoded_jwt, secret, algorithms=[_ALGO])
            valid = True
        except jwt.ExpiredSignatureError:
            pass
        except jwt.InvalidSignatureError:
            pass
    return valid, payload


def validate_credentials(username: str, password: str) -> Tuple[bool, dict]:
    pk = f"username::{username}"
    try:
        item = dynamodb_client.get_item(
            TableName=_USERS_TABLE_NAME,
            Key=ddb.to_({"pk": pk}),
        )
    except dynamodb_client.exceptions.ResourceNotFoundException:
        return False, {}

    # convert DynamoDB format to regular JSON format
    data = ddb.from_(item["Item"])

    # check if the password's hash matches
    salt: str = data["salt"]
    hashed_password = sha256((password + salt).encode(UTF_8)).hexdigest()
    if data["hashed_password"] != hashed_password:
        return False, {}

    return True, item


def validate_header(header: str) -> Tuple[bool, dict]:
    valid, payload = False, {}
    if header.startswith(_BEARER):
        return validate_jwt(header.lstrip(_BEARER).lstrip())

    return valid, payload


def error_response(message: str) -> dict:
    return {
        "isBase64Encoded": False,
        "statusCode": 400,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"error": message}),
    }


def check_authorization(func):
    @functools.wraps(func)
    def f(event: dict, context):
        # Parse event
        headers = event["headers"]
        request_context = event["requestContext"]

        # Validate header
        try:
            auth_header = headers["Authorization"]
        except:
            return error_response("Missing 'Authorization' header.")

        valid, payload = validate_header(auth_header)
        if not valid:
            return error_response("Invalid 'Authorization' token.")

        # Log event and pass into lambda handler
        parsed_event = {
            "http_method": event["httpMethod"],
            "path": event["path"],
            "headers": headers,
            "body": event["body"],
            "query_params": event["queryStringParameters"],
            "jwt_payload": payload,
            "identity": request_context["identity"],
            "request_epoch_time": request_context["requestTimeEpoch"],
        }
        print(f"Event: {json.dumps(parsed_event)}")

        return func(parsed_event, context)

    return f
