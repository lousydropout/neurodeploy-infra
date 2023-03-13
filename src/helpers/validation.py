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
_SECRETS: dict[str, str] = secrets.get_secret(_JWT_SECRET_NAME, _REGION)
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
    encoded_jwt = jwt.encode(payload, _SECRETS["current"], algorithm=_ALGO)
    return encoded_jwt, exp


def validate_auth_header(header: str) -> Tuple[bool, dict]:
    valid, payload = False, {}
    if header.startswith(_BEARER):
        return validate_jwt(header[len(_BEARER) + 1 :].lstrip())

    return valid, payload


def validate_jwt(encoded_jwt: str) -> Tuple[bool, dict]:
    valid, payload = False, {}
    for secret in (_SECRETS["current"], _SECRETS["previous"]):
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
    key = ddb.to_({"pk": username, "sk": "username"})
    try:
        item = dynamodb_client.get_item(
            TableName=_USERS_TABLE_NAME,
            Key=key,
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


def get_token_record(access_token: str) -> Dict[str, str]:
    try:
        response = dynamodb_client.get_item(
            TableName=_TOKENS_TABLE_NAME,
            Key=ddb.to_({"pk": access_token, "sk": "active"}),
        )
    except dynamodb_client.exceptions.ResourceNotFoundException:
        return False, {}

    return ddb.from_(response.get("Item", {}))


def validate_access_token(headers: Dict[str, str]) -> Tuple[bool, dict]:
    access_token = headers["access_token"]
    secret_key = headers["secret_key"]

    record = get_token_record(access_token)
    salt = record["salt"]
    hashed = record["secret_key_hash"]
    username = record["username"]

    hashed_password = sha256((secret_key + salt).encode(UTF_8)).hexdigest()

    if hashed == hashed_password:
        return True, {"username": username, "exp": None}

    return False, {}


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
        print(f"Event: {json.dumps(event)}")
        # Parse event
        headers = event.get("headers") or []
        request_context = event["requestContext"]

        # Validate header
        valid = False
        if "Authorization" in headers:
            auth_header = headers["Authorization"]
            valid, payload = validate_auth_header(auth_header)
            print("Found 'Authorization' in headers. Results: ", valid, payload)

        # If header validation failed, try validating access token
        if (
            not valid
            and "access_token" in headers
            and len(headers.get("secret_key", "")) > 10
        ):
            valid, payload = validate_access_token(headers)
            print("Found access key pair in headers. Results: ", valid, payload)

        # If still invalid, return 401
        if not valid:
            event["response"] = error_response("Invalid or expired credentials.")
            print("Event (+ error response): ", json.dumps(event, default=str))
            return event["response"]

        # Log event and pass into lambda handler
        parsed_event = {
            "http_method": event["httpMethod"],
            "path": event["path"],
            "headers": headers,
            "body": event.get("body") or "{}",
            "query_params": event.get("queryStringParameters") or {},
            "path_params": event.get("pathParameters") or {},
            "jwt_payload": payload,
            "identity": request_context["identity"],
            "request_epoch_time": request_context["requestTimeEpoch"],
        }
        print(f"Event: {json.dumps(parsed_event)}")

        return func(parsed_event, context)

    return f
