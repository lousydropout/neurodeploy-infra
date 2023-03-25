import json
from helpers import cors
from helpers import dynamodb as ddb
from helpers import validation
import boto3

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
_CREDS_TABLE_NAME = "neurodeploy_Creds"


def get_creds(username: str) -> list[dict]:
    statement = f"SELECT sk, access_key, description, expiration FROM {_CREDS_TABLE_NAME} WHERE pk='username|{username}';"
    response = dynamodb_client.execute_statement(Statement=statement)
    return [ddb.from_(x) for x in response.get("Items", [])]


@validation.check_authorization
def handler(event: dict, context):
    print("Event: ", json.dumps(event))
    username = event["username"]
    response = get_creds(username)
    creds = [{"credentials_name": item.pop("sk"), **item} for item in response]

    print("creds: ", json.dumps(creds))
    return cors.get_response(
        body={"creds": creds},
        status_code=200,
        methods="GET",
    )
