import os
import json
from helpers import dynamodb as ddb
from helpers import validation
import boto3

_REGION_NAME = os.environ["region_name"]
MODELS_S3_BUCKET = f"neurodeploy-models-{_REGION_NAME}"
LOGS_S3_BUCKET = f"neurodeploy-logs-{_REGION_NAME}"

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")

# other boto3 clients
apigw = boto3.client("apigateway")
iam = boto3.client("iam")
s3 = boto3.client("s3")


# def get_model_sort_keys(username: str, model_name: str) -> list[dict]:
#     statement = (
#         f"""SELECT sk FROM {_MODELS_TABLE_NAME} WHERE pk='{username}|{model_name}';"""
#     )
#     response = dynamodb_client.execute_statement(Statement=statement)
#     return [ddb.from_(x) for x in response.get("Items", [])]


# def delete_models(username: str, model_name: str) -> dict:
#     sort_keys = get_model_sort_keys(username, model_name)
#     statement = f"""DELETE FROM {_MODELS_TABLE_NAME} WHERE pk='{username}|{model_name}' AND sk='{{sk}}';"""
#     statements = [{"Statement": statement.format(sk=x["sk"])} for x in sort_keys]
#     print("Statements: ", statements)
#     response = dynamodb_client.batch_execute_statement(Statements=statements)
#     return response


# def get_resource_id(api_id: str, model_name: str) -> str:
#     response = apigw.get_resources(restApiId=api_id)
#     x = [y for y in response["items"] if y.get("pathPart", "") == model_name]
#     _id = x[0] if x else None
#     return _id


def delete_model(username: str, model_name: str):
    key = f"{username}/{model_name}"
    response = s3.delete_object(Bucket=MODELS_S3_BUCKET, Key=key)
    return response


@validation.check_authorization
def handler(event: dict, context):
    username = event["username"]
    model_name = event["path_params"]["proxy"]

    # Delete resource
    try:
        x = delete_model(username, model_name)
    except Exception as err:
        print(err)
        return {
            "isBase64Encoded": False,
            "statusCode": 400,
            # "headers": {"headerName": "headerValue"},
            "body": json.dumps(
                {"error_message": f"Failed to delete model {model_name}"}, default=str
            ),
        }
    print(json.dumps(x))

    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",  # Required for CORS support to work
            "Access-Control-Allow-Credentials": True,  # Required for cookies, authorization headers with HTTPS
            "Access-Control-Allow-Methods": "DELETE",  # Allow only GET request
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps({"message": f"deleted model {model_name}"}, default=str),
    }
