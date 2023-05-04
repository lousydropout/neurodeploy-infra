from typing import Tuple, Dict, Any
import os
from datetime import datetime, timedelta
import functools
from hashlib import sha256
import json

from helpers import cors, dynamodb as ddb, secrets
from helpers.logging import logger

import boto3
import jwt

_ALGO = "HS256"
_BEARER = "Bearer"  # The space at the end of the string is supposed to be there
PREFIX = os.environ["prefix"]
_REGION: str = os.environ["region_name"]
_JWT_SECRET_NAME = os.environ["jwt_secret"]
_SECRETS: dict[str, str] = secrets.get_secret(_JWT_SECRET_NAME, _REGION)
_CREDS_TABLE_NAME = f"{PREFIX}_Creds"
UTF_8 = "utf-8"

dynamo = boto3.client("dynamodb")


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


def get_creds_record(access_key: str) -> Tuple[bool, Dict[str, str]]:
    try:
        response = dynamo.get_item(
            TableName=_CREDS_TABLE_NAME,
            Key=ddb.to_({"pk": f"creds|{access_key}", "sk": "creds"}),
        )
    except dynamo.exceptions.ResourceNotFoundException:
        return False, {}

    items = ddb.from_(response.get("Item", {}))
    if not items:
        return False, {}

    return True, items


def validate_credentials(headers: Dict[str, str]) -> Tuple[bool, dict]:
    access_key = headers["access_key"]
    secret_key = headers["secret_key"]

    success, record = get_creds_record(access_key)
    if not success:
        return False, {}
    salt = record["salt"]
    hashed = record["secret_key_hash"]
    username = record["username"]

    hashed_password = sha256((secret_key + salt).encode(UTF_8)).hexdigest()

    if hashed == hashed_password:
        return True, {"username": username, "expiration": None}

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
        try:
            return g(event, context)
        except Exception as err:
            logger.exception("Error at validation: %s", err)
            return cors.get_response(
                body={"error": "Unable to validate user"},
                status_code=500,
                headers="*",
                methods="POST",
            )

    @functools.wraps(f)
    def g(event: dict, context):
        # Parse event
        headers = event.get("headers") or {}
        request_context = event["requestContext"]

        # Validate header
        payload = {}
        valid = False
        if "Authorization" in headers:
            auth_header = headers["Authorization"]
            valid, payload = validate_auth_header(auth_header)
            del headers["Authorization"]  # remove Authorization from headers
            logger.debug(
                "Found 'Authorization' in headers. Results: %s, %s", valid, payload
            )

        # If header validation failed, try validating access token
        if (
            not valid
            and "access_key" in headers
            and len(headers.get("secret_key", "")) > 10
        ):
            valid, payload = validate_credentials(headers)
            del headers["secret_key"]  # remove secret_key from headers
            logger.debug(
                "Found access key pair in headers. Results: %s, %s", valid, payload
            )

        # If still invalid, return 401
        if not valid:
            event["response"] = error_response("Invalid or expired credentials.")
            logger.debug("Event (+ error response): %s", json.dumps(event, default=str))
            return event["response"]

        #
        query_params = event.get("queryStringParameters") or {}
        body = event.get("body") or "{}"
        body_json = json.loads(body)

        # Log event and pass into lambda handler
        username = payload["username"]
        parsed_event = {
            "http_method": event["httpMethod"],
            "path": event["path"],
            "headers": headers,
            "body": body,
            "query_params": query_params,
            "path_params": event.get("pathParameters") or {},
            "params": {**query_params, **headers, **body_json},
            "username": username,
            "identity": request_context["identity"],
            "request_epoch_time": request_context["requestTimeEpoch"],
        }
        logger.debug(f"Event (after validation): %s", json.dumps(parsed_event))

        return func(parsed_event, context)

    return f
