import os
import json
from hashlib import sha256
from uuid import uuid4 as uuid
import boto3

UTF_8 = "utf-8"


_USERS = os.environ["neurodeploy_Users"]
_QUEUE = os.environ["queue"]


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
    pass
    # if user already exists, throw exception


def handler(event: dict, context) -> dict:
    # 1. Parse event
    try:
        parsed_event = parse(event)
        print(f"Event: {json.dumps(parsed_event)}")
    except Exception as err:
        print(err)
        return {
            "isBase64Encoded": False,
            "statusCode": 400,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"message": "Bad input", "error": str(err)}),
        }

    # 2. Log user info to DynamoDB

    # 3. Create auth token & log record

    # 4. Create API route for /username/ping

    return {
        "isBase64Encoded": False,
        "statusCode": 201,
        "headers": {"content-type": "application/json"},
        "body": "...",
    }
