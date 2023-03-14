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
    access_token: str,
    secret_key: str,
    description: str,
):
    try:
        salt = uuid().hex
        # username
        record = {
            "pk": f"username|{username}",
            "sk": access_token,
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
            "secret_key_hash": sha256((secret_key + salt).encode(UTF_8)).hexdigest(),
            "salt": salt,
            "description": description,
        }
        _TOKENS_TABLE.put_item(
            Item=record,
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
    except dynamodb_client.exceptions.ConditionalCheckFailedException:
        raise Exception(f"""The access key for "{access_token}" already exists.""")


def is_valid(access_token: str) -> bool:
    # validate model_name
    remaining = set(access_token).difference(
        set(string.ascii_letters + string.digits + "-_")
    )
    return not remaining


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
    body = json.loads(event["body"])
    params = event["query_params"] or body
    try:
        description = params["description"]
    except Exception:
        return {
            "isBase64Encoded": False,
            "statusCode": 400,
            "body": json.dumps(
                {
                    "errorMessage": "Missing param: 'description' must be included in the body json."
                }
            ),
        }

    access_token = uuid().hex
    secret_key = sha256(uuid().hex.encode(UTF_8)).hexdigest()
    try:
        response = add_token_to_tokens_table(
            username=username,
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
        "body": json.dumps({"access_token": access_token, "secret_key": secret_key}),
    }
