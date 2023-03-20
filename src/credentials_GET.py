import json
from helpers import dynamodb as ddb
from helpers import validation
import boto3

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
_TOKENS_TABLE_NAME = "neurodeploy_Tokens"


def get_tokens(username: str) -> list[dict]:
    statement = f"SELECT sk, access_token, description, expiration FROM {_TOKENS_TABLE_NAME} WHERE pk='username|{username}';"
    response = dynamodb_client.execute_statement(Statement=statement)
    return [ddb.from_(x) for x in response.get("Items", [])]


@validation.check_authorization
def handler(event: dict, context):
    print("Event: ", json.dumps(event))
    username = event["username"]
    response = get_tokens(username)
    tokens = [{"crendential_name": item.pop("sk"), **item} for item in response]

    print("Tokens: ", json.dumps(tokens))
    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",  # Required for CORS support to work
            "Access-Control-Allow-Credentials": True,  # Required for cookies, authorization headers with HTTPS
            "Access-Control-Allow-Methods": "GET",  # Allow only GET request
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps({"tokens": tokens}),
    }
