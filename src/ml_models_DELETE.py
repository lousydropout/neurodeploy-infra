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
_APIS_TABLE_NAME = "neurodeploy_Apis"
_MODELS_TABLE_NAME = "neurodeploy_Models"

# other boto3 clients
apigw = boto3.client("apigateway")
iam = boto3.client("iam")
s3 = boto3.client("s3")


def get_model_sort_keys(username: str, model_name: str) -> list[dict]:
    statement = (
        f"""SELECT sk FROM {_MODELS_TABLE_NAME} WHERE pk='{username}|{model_name}';"""
    )
    response = dynamodb_client.execute_statement(Statement=statement)
    return [ddb.from_(x) for x in response.get("Items", [])]


def delete_models(username: str, model_name: str) -> dict:
    sort_keys = get_model_sort_keys(username, model_name)
    statement = f"""DELETE FROM {_MODELS_TABLE_NAME} WHERE pk='{username}|{model_name}' AND sk='{{sk}}';"""
    statements = [{"Statement": statement.format(sk=x["sk"])} for x in sort_keys]
    print("Statements: ", statements)
    response = dynamodb_client.batch_execute_statement(Statements=statements)
    return response


def get_resource_id(api_id: str, model_name: str) -> str:
    response = apigw.get_resources(restApiId=api_id)
    _id = next(
        y["id"] for y in response["items"] if y.get("pathPart", "") == model_name
    )
    return _id


def delete_model(username: str, model_name: str):
    # get restapi_id for user
    statement = f"""SELECT api_id FROM {_APIS_TABLE_NAME} WHERE pk='{username}' AND sk='resources';"""
    response = dynamodb_client.execute_statement(Statement=statement)
    api_ids = [ddb.from_(x) for x in response.get("Items", [])]
    print("Api ids: ", api_ids)
    api_id = next(y["api_id"] for y in api_ids if "api_id" in y)
    print("Api id: ", api_id)
    # get resource id for model_name
    resource_id = get_resource_id(api_id=api_id, model_name=model_name)
    print("resource_id: ", resource_id)
    # delete resource
    response = apigw.delete_resource(restApiId=api_id, resourceId=resource_id)
    return response


@validation.check_authorization
def handler(event: dict, context):
    jwt_payload = event["jwt_payload"]
    username = jwt_payload["username"]

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

    return {
        "isBase64Encoded": False,
        "statusCode": 204,
        # "headers": {"headerName": "headerValue"},
        "body": json.dumps({"message": f"deleted model {model_name}"}, default=str),
    }
