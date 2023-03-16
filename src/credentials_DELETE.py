import json
from helpers import dynamodb as ddb
from helpers import validation
import boto3

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
_TOKENS_TABLE_NAME = "neurodeploy_Tokens"


def delete_credential(username: str, credential_name) -> list[dict]:
    # Get access_token using username & credential_name
    statement = f"SELECT access_token FROM {_TOKENS_TABLE_NAME} WHERE pk='username|{username}' and sk='{credential_name}';"
    response = dynamodb_client.execute_statement(Statement=statement)
    result = [ddb.from_(x) for x in response.get("Items", [])]
    access_token = result[0]["access_token"]

    # Delete relevant records from dynamodb
    _statements = [
        f"DELETE FROM {_TOKENS_TABLE_NAME} WHERE pk='username|{username}' and sk='{credential_name}';",
        f"DELETE FROM {_TOKENS_TABLE_NAME} WHERE pk='access_token|{access_token}' and sk='access_token';",
    ]
    statements = [{"Statement": statement} for statement in _statements]
    response = dynamodb_client.batch_execute_statement(Statements=statements)
    return [ddb.from_(x) for x in response.get("Items", [])]


@validation.check_authorization
def handler(event: dict, context):
    username = event["username"]
    credential_name = event["path_params"]["proxy"]
    response = delete_credential(username, credential_name)

    print("response: ", json.dumps(response, default=str))

    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": json.dumps(
            {"message": f"Deleted user {username}'s credential '{credential_name}'."},
            default=str,
        ),
    }
