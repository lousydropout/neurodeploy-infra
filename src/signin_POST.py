import os
from typing import Tuple
import json
from hashlib import sha256
import boto3
from helpers import cors, dynamodb as ddb, validation
from helpers.decimal_encoder import DecimalEncoder
from helpers.logging import logger
from api_keys_POST import insert_api_key_record

PREFIX = os.environ["prefix"]

dynamodb = boto3.client("dynamodb")

UTF_8 = "utf-8"
_USERS_TABLE_NAME = f"{PREFIX}_Users"


def is_password_correct(password: str, salt: str, hashed: str) -> bool:
    return sha256((password + salt).encode(UTF_8)).hexdigest() == hashed


def parse(event: dict) -> Tuple[dict, dict]:
    """Return a parsed version of the API Gateway event (with password salted and hashed)."""
    # get headers
    headers: dict[str, str] = event.get("headers") or {}
    if "username" not in headers or "password" not in headers:
        raise Exception(
            "One or more of the required fields, 'username' and 'password,' is/are missing."
        )

    # other stuff
    request_context = event["requestContext"]
    identity = request_context["identity"]

    parsed_event = {
        "http_method": event["httpMethod"],
        "path": event["path"],
        "query_params": event["queryStringParameters"],
        "protocol": request_context["protocol"],
        "domain_name": request_context["domainName"],
        "request_epoch_time": request_context["requestTimeEpoch"],
        "api_id": request_context["apiId"],
        "stage": request_context["stage"],
        "ip_source": identity["sourceIp"],
        "identity": identity,
    }

    return headers, parsed_event


def get_user(username: str) -> dict:
    response: dict = dynamodb.get_item(
        TableName=_USERS_TABLE_NAME,
        Key=ddb.to_({"pk": username, "sk": "username"}),
    )
    items = response.get("Item", {})
    return ddb.from_(items)


def get_error_response(err: Exception | str) -> dict:
    return cors.get_response(
        status_code=400,
        body={"error_message": str(err)},
        methods="POST",
    )


def handler(event: dict, context):
    # 1. Parse event
    try:
        headers, parsed_event = parse(event)
        print(f"Event: {json.dumps(parsed_event)}")
    except Exception as err:
        logger.exception(err)
        response = get_error_response(err)
        print("Response: ", json.dumps(response))
        return response

    # 2. Get record
    try:
        user = get_user(headers["username"])
        print(f"User: {json.dumps(user, cls=DecimalEncoder)}")
    except Exception as err:
        logger.exception(err)
        response = get_error_response(err)
        print("Response: ", json.dumps(response))
        return response

    if not user:
        return get_error_response("Incorrect username/password combination")

    # 3. Check if the password is correct
    if is_password_correct(
        password=headers["password"],
        salt=user["salt"],
        hashed=user["hashed_password"],
    ):
        print(f"Password is correct: True")
    else:
        response = get_error_response("Incorrect username/password combination")
        print("Response: ", json.dumps(response))
        return response

    # 4. Create jwt
    print("create jwt token", end=". . . ")
    token, exp = validation.create_api_token(username=headers["username"])
    print("done")

    # 5. Create quickly expiring api key
    api_key = insert_api_key_record(
        username=headers["username"],
        model_name="*",
        description="for temporary purposes",
        expiration=60 * 24,  # minutes
    )

    # 6. Return jwt
    return cors.get_response(
        status_code=200,
        body={"token": token, "expiration": exp.isoformat(), "api-key": api_key},
        methods="POST",
    )
