import os
import json
from hashlib import sha256
from uuid import uuid4 as uuid
from helpers import validation

import boto3


UTF_8 = "utf-8"
_USERS_TABLE_NAME = "neurodeploy_Users"
_API_TOKENS_TABLE_NAME = "neurodeploy_Tokens"
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
_USERS_TABLE = dynamodb.Table(_USERS_TABLE_NAME)
_TOKENS_TABLE = dynamodb.Table(_API_TOKENS_TABLE_NAME)

_DOMAIN_NAME = os.environ["domain_name"]
_QUEUE = os.environ["queue"]
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


def add_token_to_tokens_table(
    username: str, credential_name: str, access_token: str, secret_key: str
):
    try:
        salt = uuid().hex
        # username
        record = {
            "pk": f"username|{username}",
            "sk": credential_name,
            "access_token": access_token,
            "description": "default access key + access secret pair",
            "expiration": None,
        }
        _TOKENS_TABLE.put_item(
            Item=record,
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        # access-token
        record = {
            "pk": f"access_token|{access_token}",
            "sk": "access_token",
            "credential_name": credential_name,
            "username": username,
            "secret_key_hash": sha256((secret_key + salt).encode(UTF_8)).hexdigest(),
            "salt": salt,
            "description": "default access key + access secret pair",
            "expiration": None,
        }
        _TOKENS_TABLE.put_item(
            Item=record,
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
    except dynamodb_client.exceptions.ConditionalCheckFailedException:
        raise Exception(f"""The access key for "{access_token}" already exists.""")


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
    return {
        "isBase64Encoded": False,
        "statusCode": 400,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"error": str(err)}),
    }


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

    # 3. Create auth token & log record
    print("3. creating default access token and secret key", end=". . . ")
    access_token = uuid().hex
    secret_key = sha256(uuid().hex.encode(UTF_8)).hexdigest()
    try:
        add_token_to_tokens_table(
            username=username,
            credential_name="default",
            access_token=access_token,
            secret_key=secret_key,
        )
    except Exception as err:
        print("failed")
        print(err)
        response = get_error_response(err)
        print("Response: ", json.dumps(response))
        return response
    print("done")

    # 4. Create jwt
    print("create jwt token", end=". . . ")
    token, exp = validation.create_api_token(username=username)
    print("done")

    # 4. Send event to queue to create api for new user
    # payload = {"domain_name": _DOMAIN_NAME, "username": username}
    # response = sqs.send_message(
    #     QueueUrl=_QUEUE,
    #     MessageGroupId=username,
    #     MessageDeduplicationId=str(uuid()),
    #     MessageBody=json.dumps(payload),
    # )
    # print("Sqs send messsage response: ", json.dumps(response, default=str))

    # 5. Return response
    response = {
        "isBase64Encoded": False,
        "statusCode": 201,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",  # Required for CORS support to work
            "Access-Control-Allow-Credentials": True,  # Required for cookies, authorization headers with HTTPS
            "Access-Control-Allow-Methods": "POST",  # Allow only POST request
            "Access-Control-Allow-Headers": "*",
        },
        "body": json.dumps(
            {
                "name": "default",
                "access_token": access_token,
                "secret_key": secret_key,
                "expiration": None,
                "jwt": {"token": token, "expiration": exp.isoformat()},
            }
        ),
    }
    print("Response: ", json.dumps(response))
    return response
