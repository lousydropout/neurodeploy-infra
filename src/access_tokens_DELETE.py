import json
from helpers import dynamodb as ddb
from helpers import validation
import boto3

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
_TOKENS_TABLE_NAME = "neurodeploy_Tokens"


def delete_token(username: str, token_name) -> list[dict]:
    statements = [
        {
            "Statement": f"DELETE FROM {_TOKENS_TABLE_NAME} WHERE pk='username|{username}' and sk='{token_name}';"
        },
        {
            "Statement": f"DELETE FROM {_TOKENS_TABLE_NAME} WHERE pk='access_token|{token_name}' and sk='access_token';"
        },
    ]
    response = dynamodb_client.batch_execute_statement(Statements=statements)
    return [ddb.from_(x) for x in response.get("Items", [])]


@validation.check_authorization
def handler(event: dict, context):
    username = event["username"]
    token_name = event["path_params"]["proxy"]
    response = delete_token(username, token_name)

    print("response: ", json.dumps(response, default=str))

    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": json.dumps({"response": response}, default=str),
    }
