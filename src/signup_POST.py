import os
import json
from hashlib import sha256
from uuid import uuid4 as uuid
from helpers import cors, validation

import boto3


PREFIX = os.environ["prefix"]
UTF_8 = "utf-8"
_USERS_TABLE_NAME = f"{PREFIX}_Users"
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
_USERS_TABLE = dynamodb.Table(_USERS_TABLE_NAME)

sqs = boto3.client("sqs")


def parse(event: dict) -> dict:
    """Return a parsed version of the API Gateway event (with password salted and hashed)."""
    # get header
    headers: dict[str, str] = event.get("headers") or {}

    # remove password from headers since headers will be logged
    password = headers.pop("password")
    # validate password & create hash
    if len(password) < 8:
        raise Exception("Password not long enough (min: 8 characters long)")
    salt = str(uuid())
    hashed_password: str = sha256((password + salt).encode(UTF_8)).hexdigest()

    # other stuff
    request_context = event["requestContext"]
    identity = request_context["identity"]

    return {
        "http_method": event["httpMethod"],
        "path": event["path"],
        "query_params": event["queryStringParameters"],
        "headers": headers,
        "protocol": request_context["protocol"],
        "domain_name": request_context["domainName"],
        "request_epoch_time": request_context["requestTimeEpoch"],
        "api_id": request_context["apiId"],
        "stage": request_context["stage"],
        "ip_source": identity["sourceIp"],
        "username": headers["username"],
        "email": headers["email"],
        "salt": salt,
        "hashed_password": hashed_password,
        "identity": identity,
    }


def add_user_to_users_table(username: str, payload: dict):
    try:
        record = {"pk": username, "sk": "username", **payload}
        _USERS_TABLE.put_item(
            Item=record,
            ConditionExpression="attribute_not_exists(pk)",
        )
    except dynamodb_client.exceptions.ConditionalCheckFailedException:
        raise Exception(f"""The username "{username}" already exists.""")


def get_number_of_users() -> int:
    response = dynamodb_client.scan(
        TableName=_USERS_TABLE,
        Limit=101,
        Select="SPECIFIC_ATTRIBUTES",
        ProjectionExpression="pk",
        ConsistentRead=False,
    )
    print("users: ", json.dumps(response))
    num_users = response["ScannedCount"]
    return num_users


def get_error_response(err: Exception) -> dict:
    return cors.get_response(
        status_code=400,
        body={"error_message": str(err)},
        methods="POST",
    )


def handler(event: dict, context) -> dict:
    # 1. Parse event
    print("1. parsing event", end=". . . ")
    try:
        parsed_event = parse(event)
    except Exception as err:
        print("failed")
        print(err)
        response = get_error_response(err)
        print("Response: ", json.dumps(response))
        return response
    print("done")
    print(f"Event: {json.dumps(parsed_event)}")

    # 2. Log user info to DynamoDB
    print("2. creating user", end=". . . ")
    try:
        username = parsed_event["username"]
        add_user_to_users_table(username, parsed_event)
    except Exception as err:
        print("failed")
        print(err)
        response = get_error_response(err)
        print("Response: ", json.dumps(response))
        return response
    print("done")

    # 3. Create jwt
    print("3. create jwt token", end=". . . ")
    token, exp = validation.create_api_token(username=username)
    print("done")

    # 4. Return response
    response = cors.get_response(
        status_code=201,
        body={
            "username": username,
            "jwt": {"token": token, "expiration": exp.isoformat()},
        },
        methods="POST",
    )
    print("Response: ", json.dumps(response))
    return response
