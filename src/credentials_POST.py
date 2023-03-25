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
_CREDS_TABLE_NAME = "neurodeploy_Creds"
_CREDS_TABLE = dynamodb.Table(_CREDS_TABLE_NAME)


def add_creds_to_table(
    username: str,
    credentials_name: str,
    access_key: str,
    secret_key: str,
    description: str,
    expiration: str,
):
    try:
        salt = uuid().hex
        # username
        record = {
            "pk": f"username|{username}",
            "sk": credentials_name,
            "access_key": access_key,
            "description": description,
            "expiration": expiration,
        }
        _CREDS_TABLE.put_item(
            Item=record,
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        # access-token
        record = {
            "pk": f"creds|{access_key}",
            "sk": "creds",
            "username": username,
            "credentials_name": credentials_name,
            "expiration": expiration,
            "secret_key_hash": sha256((secret_key + salt).encode(UTF_8)).hexdigest(),
            "salt": salt,
            "description": description,
        }
        _CREDS_TABLE.put_item(
            Item=record,
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
    except dynamodb_client.exceptions.ConditionalCheckFailedException:
        raise Exception(
            f"""The credentials_name for "{credentials_name}" already exists."""
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
        credentials_name = params["credentials_name"]
    except Exception:
        return cors.get_response(
            status_code=400,
            body={
                "error_message": "Missing param: 'credentials_name' must be included in the headers."
            },
            methods="POST",
        )
    error = is_invalid(credentials_name)
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

    access_key = uuid().hex
    secret_key = sha256(uuid().hex.encode(UTF_8)).hexdigest()
    expiration = None
    try:
        response = add_creds_to_table(
            username=username,
            credentials_name=credentials_name,
            access_key=access_key,
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
            "credentials_name": credentials_name,
            "description": description,
            "access_key": access_key,
            "secret_key": secret_key,
            "expiration": None,
        },
    )
