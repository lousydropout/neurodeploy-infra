import os
from typing import Tuple
import json
from hashlib import sha256
import boto3
from helpers import validation
from helpers import dynamodb as ddb
from helpers.decimalEncoder import DecimalEncoder


dynamodb = boto3.client("dynamodb")

UTF_8 = "utf-8"
_USERS_TABLE_NAME = "neurodeploy_Users"
_USERS = os.environ[_USERS_TABLE_NAME]
_TOKENS = os.environ["neurodeploy_Tokens"]


def is_password_correct(password: str, salt: str, hashed: str) -> bool:
    return sha256((password + salt).encode(UTF_8)).hexdigest() == hashed


def parse(event: dict) -> Tuple[dict, dict]:
    """Return a parsed version of the API Gateway event (with password salted and hashed)."""
    # get body
    body: dict[str, str] = json.loads(event["body"])
    if "username" not in body or "password" not in body:
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
    response: dict = dynamodb.get_item(
        TableName=_USERS_TABLE_NAME,
        Key=ddb.to_({"pk": username, "sk": "username"}),
    )
    items = response.get("Item", {})
    return ddb.from_(items)


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

    # 4. Create jwt
    print("create jwt token", end=". . . ")
    token, exp = validation.create_api_token(username=body["username"])
    print("done")

    # 5. Return jwt
    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"token": token, "expiration": exp.isoformat()}),
    }
