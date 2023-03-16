import json
import string
from hashlib import sha256
from uuid import uuid4 as uuid
from helpers import validation
import boto3

UTF_8 = "utf-8"

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
_TOKENS_TABLE_NAME = "neurodeploy_Tokens"
_TOKENS_TABLE = dynamodb.Table(_TOKENS_TABLE_NAME)


def add_token_to_tokens_table(
    username: str,
    credential_name: str,
    access_token: str,
    secret_key: str,
    description: str,
):
    try:
        salt = uuid().hex
        # username
        record = {
            "pk": f"username|{username}",
            "sk": credential_name,
            "access_token": access_token,
            "description": description,
        }
        _TOKENS_TABLE.put_item(
            Item=record,
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        # access-token
        record = {
            "pk": f"access_token|{access_token}",
            "sk": "access_token",
            "username": username,
            "credential_name": credential_name,
            "secret_key_hash": sha256((secret_key + salt).encode(UTF_8)).hexdigest(),
            "salt": salt,
            "description": description,
        }
        _TOKENS_TABLE.put_item(
            Item=record,
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
    except dynamodb_client.exceptions.ConditionalCheckFailedException:
        raise Exception(
            f"""The credential_name for "{credential_name}" already exists."""
        )


def is_invalid(credential_name: str) -> str:
    # validate credental_name
    remaining = set(credential_name).difference(
        set(string.ascii_letters + string.digits + "-_")
    )
    if remaining:
        return "Invalid credental_name: Only alphanumeric characters [A-Za-z0-9], hyphens ('-'), and underscores ('_') are allowed."
    return None


def get_error_response(err: Exception) -> dict:
    return {
        "isBase64Encoded": False,
        "statusCode": 400,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"error": str(err)}),
    }


@validation.check_authorization
def handler(event: dict, context):
    print("Event: ", json.dumps(event))
    username = event["username"]
    headers = event["headers"]
    params = event["query_params"] or headers
    try:
        credential_name = params["credential_name"]
    except Exception:
        return {
            "isBase64Encoded": False,
            "statusCode": 400,
            "body": json.dumps(
                {
                    "errorMessage": "Missing param: 'credential_name' must be included in the headers."
                }
            ),
        }
    error = is_invalid(credential_name)
    if error:
        return {
            "isBase64Encoded": False,
            "statusCode": 400,
            "body": json.dumps({"errorMessage": error}),
        }

    try:
        description = params["description"]
    except Exception:
        return {
            "isBase64Encoded": False,
            "statusCode": 400,
            "body": json.dumps(
                {
                    "errorMessage": "Missing param: 'description' must be included in the headers."
                }
            ),
        }

    access_token = uuid().hex
    secret_key = sha256(uuid().hex.encode(UTF_8)).hexdigest()
    try:
        response = add_token_to_tokens_table(
            username=username,
            credential_name=credential_name,
            access_token=access_token,
            secret_key=secret_key,
            description=description,
        )
    except Exception as err:
        print("failed")
        print(err)
        response = get_error_response(err)
        print("Response: ", json.dumps(response))
        return response

    print("Response: ", json.dumps(response))
    return {
        "isBase64Encoded": False,
        "statusCode": 201,
        "body": json.dumps(
            {
                "access_token": access_token,
                "secret_key": secret_key,
                "credential_name": credential_name,
                "expiration": None,
                "description": description,
            }
        ),
    }
