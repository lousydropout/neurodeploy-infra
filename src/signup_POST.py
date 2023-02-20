import os
import json
from hashlib import sha256
from uuid import uuid4 as uuid
import boto3


UTF_8 = "utf-8"
_USERS_TABLE_NAME = "neurodeploy_Users"
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
_USERS_TABLE = dynamodb.Table(_USERS_TABLE_NAME)


def parse(event: dict) -> dict:
    """Return a parsed version of the API Gateway event (with password salted and hashed)."""
    # get body
    body: dict[str, str] = json.loads(event["body"])

    password = body["password"]
    if len(password) < 8:
        raise Exception("Password not long enough")
    salt = str(uuid())
    hashed_password: str = sha256((password + salt).encode(UTF_8)).hexdigest()

    # other stuff
    request_context = event["requestContext"]
    identity = request_context["identity"]

    return {
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
        "username": body["username"],
        "email": body["email"],
        "salt": salt,
        "hashed_password": hashed_password,
        "identity": identity,
    }


def add_user_to_users_table(username: str, payload: dict):
    try:
        record = {"pk": f"username::{username}", **payload}
        _USERS_TABLE.put_item(
            Item=record,
            ConditionExpression="attribute_not_exists(pk)",
        )
    except dynamodb_client.exceptions.ConditionalCheckFailedException:
        raise Exception(f"""The username "{username}" already exists.""")


def get_error_response(err: Exception) -> dict:
    return {
        "isBase64Encoded": False,
        "statusCode": 400,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"error": str(err)}),
    }


def handler(event: dict, context) -> dict:
    # 1. Parse event
    try:
        parsed_event = parse(event)
        print(f"Event: {json.dumps(parsed_event)}")
    except Exception as err:
        print(err)
        response = get_error_response(err)
        print("Response: ", json.dumps(response))
        return response

    # 2. Log user info to DynamoDB
    try:
        add_user_to_users_table(parsed_event["username"], parsed_event)
    except Exception as err:
        print(err)
        response = get_error_response(err)
        print("Response: ", json.dumps(response))
        return response

    # 3. Create auth token & log record

    # 4. Create API route for /username/ping

    response = {
        "isBase64Encoded": False,
        "statusCode": 201,
        "headers": {"content-type": "application/json"},
        "body": "...",
    }
    print("Response: ", json.dumps(response))
    return response
