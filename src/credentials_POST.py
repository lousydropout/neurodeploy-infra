import json
import string
from hashlib import sha256
from uuid import uuid4 as uuid
from helpers import cors
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
    expiration: str,
):
    try:
        salt = uuid().hex
        # username
        record = {
            "pk": f"username|{username}",
            "sk": credential_name,
            "access_token": access_token,
            "description": description,
            "expiration": expiration,
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
            "expiration": expiration,
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


@validation.check_authorization
def handler(event: dict, context):
    print("Event: ", json.dumps(event))
    username = event["username"]
    headers = event["headers"]
    params = event["query_params"] or headers
    try:
        credential_name = params["credential_name"]
    except Exception:
        return cors.get_response(
            status_code=400,
            body={
                "error_message": "Missing param: 'credential_name' must be included in the headers."
            },
            methods="POST",
        )
    error = is_invalid(credential_name)
    if error:
        return cors.get_response(
            status_code=400,
            body={"errorMessage": error},
            methods="POST",
        )

    try:
        description = params["description"]
    except Exception:
        return cors.get_response(
            status_code=400,
            body={
                "error_message": "Missing param: 'description' must be included in the headers."
            },
        )

    access_token = uuid().hex
    secret_key = sha256(uuid().hex.encode(UTF_8)).hexdigest()
    expiration = None
    try:
        response = add_token_to_tokens_table(
            username=username,
            credential_name=credential_name,
            access_token=access_token,
            secret_key=secret_key,
            description=description,
            expiration=expiration,
        )
    except Exception as err:
        print("failed")
        print(err)
        response = cors.get_response(
            status_code=400, body={"error_message": err}, methods="POST"
        )
        print("Response: ", json.dumps(response))
        return response

    print("Response: ", json.dumps(response))
    return cors.get_response(
        status_code=201,
        methods="POST",
        body={
            "access_token": access_token,
            "secret_key": secret_key,
            "credential_name": credential_name,
            "expiration": None,
            "description": description,
        },
    )
