from typing import Tuple, Dict
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
_TOKENS_TABLE_NAME = "neurodeploy_Tokens"
UTF_8 = "utf-8"

dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
_USERS_TABLE = dynamodb.Table(_USERS_TABLE_NAME)
_TOKENS_TABLE = dynamodb.Table(_TOKENS_TABLE_NAME)


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


def get_token_record(access_key: str) -> Dict[str, str]:
    try:
        response = dynamodb_client.get_item(
            TableName=_TOKENS_TABLE_NAME,
            Key=ddb.to_({"pk": access_key}),
        )
    except dynamodb_client.exceptions.ResourceNotFoundException:
        return False, {}

    return ddb.from_(response.get("Item", {}))


def validate_access_token(body: Dict[str, str]) -> Tuple[bool, dict]:
    access_key = body["access_key"]
    access_secret = body["access_secret"]

    record = get_token_record(access_key)
    salt = record["salt"]
    hashed = record["access_secret_hash"]
    username = record["username"]

    hashed_password = sha256((access_secret + salt).encode(UTF_8)).hexdigest()

    if hashed == hashed_password:
        return True, {"username": username, "exp": None}

    return False, {}


def check_authorization(func):
    @functools.wraps(func)
    def f(event: dict, context):
        # Parse event
        headers = event["headers"]
        body = event["body"]
        request_context = event["requestContext"]

        # Validate header
        auth_header = headers.get("Authorization", "")
        valid, payload = validate_header(auth_header)

        # If header validation failed, try validating access token
        if not valid:
            valid, payload = validate_access_token(body)

        # If still invalid, return 401
        if not valid:
            return error_response("Invalid or expired credentials.")

        # Log event and pass into lambda handler
        parsed_event = {
            "http_method": event["httpMethod"],
            "path": event["path"],
            "headers": headers,
            "body": body,
            "query_params": event["queryStringParameters"],
            "jwt_payload": payload,
            "identity": request_context["identity"],
            "request_epoch_time": request_context["requestTimeEpoch"],
        }
        print(f"Event: {json.dumps(parsed_event)}")

        return func(parsed_event, context)

    return f
