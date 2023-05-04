import os
import json
from helpers import cors, dynamodb as ddb, validation
from helpers.logging import logger
import boto3

PREFIX = os.environ["prefix"]

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
_CREDS_TABLE_NAME = f"{PREFIX}_Creds"


def delete_credential(username: str, credential_name) -> list[dict]:
    # Get access_key using username & credential_name
    statement = f"SELECT access_key FROM {_CREDS_TABLE_NAME} WHERE pk='username|{username}' and sk='{credential_name}';"
    response = dynamodb_client.execute_statement(Statement=statement)
    result = [ddb.from_(x) for x in response.get("Items", [])]
    access_key = result[0]["access_key"]

    # Delete relevant records from dynamodb
    _statements = [
        f"DELETE FROM {_CREDS_TABLE_NAME} WHERE pk='username|{username}' and sk='{credential_name}';",
        f"DELETE FROM {_CREDS_TABLE_NAME} WHERE pk='creds|{access_key}' and sk='creds';",
    ]
    statements = [{"Statement": statement} for statement in _statements]
    response = dynamodb_client.batch_execute_statement(Statements=statements)
    return [ddb.from_(x) for x in response.get("Items", [])]


@validation.check_authorization
def handler(event: dict, context):
    username = event["username"]
    credential_name = event["path_params"]["credential_name"]

    try:
        response = delete_credential(username, credential_name)
    except:
        return cors.get_response(
            status_code=200,
            body={
                "error_message": f"Unable to delete credentials '{credential_name}'. Please confirm credential's name."
            },
        )

    logger.info("response: %s", json.dumps(response, default=str))

    return cors.get_response(
        status_code=200,
        body={"message": f"Deleted user {username}'s credential '{credential_name}'."},
        methods="DELETE",
    )
