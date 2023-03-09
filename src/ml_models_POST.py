import os
import json
from helpers import dynamodb as ddb
from helpers import validation
import boto3
from botocore.exceptions import ClientError

_ACCOUNT_NUMBER = os.environ["account_number"]
_REGION_NAME = os.environ["region_name"]
PROXY_LAMBDA_NAME = os.environ["proxy_lambda"]
MODELS_S3_BUCKET = f"neurodeploy-models-{_REGION_NAME}"
LOGS_S3_BUCKET = f"neurodeploy-logs-{_REGION_NAME}"

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
_APIS_TABLE_NAME = "neurodeploy_Apis"
_API_TABLE = dynamodb.Table(_APIS_TABLE_NAME)
_MODELS_TABLE_NAME = "neurodeploy_Models"
_MODEL_TABLE = dynamodb.Table(_MODELS_TABLE_NAME)

# other boto3 clients
apigw = boto3.client("apigateway")
iam = boto3.client("iam")
s3 = boto3.client("s3")


def get_api_record(username: str) -> dict:
    key = ddb.to_({"pk": username, "sk": _REGION_NAME})
    response = dynamodb_client.get_item(TableName=_APIS_TABLE_NAME, Key=key)
    return ddb.from_(response.get("Item", {}))


def add_integration_method(
    api_id: str,
    resource_id: str,
    rest_method: str,
    function_name: str,
):
    try:
        apigw.put_method(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod=rest_method,
            authorizationType="NONE",
        )
        apigw.put_method_response(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod=rest_method,
            statusCode="200",
            responseModels={"application/json": "Empty"},
        )
        print("Created %s method for resource %s.", rest_method, resource_id)
    except ClientError:
        print("Couldn't create %s method for resource %s.", rest_method, resource_id)
        raise

    uri = f"arn:aws:apigateway:{_REGION_NAME}:lambda:path/2015-03-31/functions/arn:aws:lambda:{_REGION_NAME}:{_ACCOUNT_NUMBER}:function:{function_name}/invocations"

    try:
        apigw.put_integration(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod=rest_method,
            type="AWS_PROXY",
            integrationHttpMethod="POST",
            requestTemplates={"application/json": json.dumps({})},
            uri=uri,
            passthroughBehavior="WHEN_NO_TEMPLATES",
        )
        apigw.put_integration_response(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod=rest_method,
            statusCode="200",
            responseTemplates={"application/json": ""},
        )
        print("Created integration for resource: ", resource_id)
    except ClientError:
        print("Couldn't create integration for resource: ", resource_id)
        raise

    # create deployment (apigw must contain method)
    _ = apigw.create_deployment(
        restApiId=api_id,
        stageName="prod",
        tracingEnabled=False,
    )


@validation.check_authorization
def handler(event: dict, context):
    # body = json.loads(event["body"]) if event["body"] else {}
    # query_params = event["query_params"]

    jwt_payload = event["jwt_payload"]
    username = jwt_payload["username"]

    api_record = get_api_record(username)
    resources = api_record["resources"]
    api_id = resources["rest_api_id"]
    root_id = resources["root_id"]

    model_name = event["path_params"]["proxy"]

    # Create resource
    try:
        ping = apigw.create_resource(
            restApiId=api_id,
            parentId=root_id,
            pathPart=model_name,
        )
    except apigw.exceptions.ConflictException as err:
        print("Err: ", err)
        return {
            "isBase64Encoded": False,
            "statusCode": 400,
            "body": json.dumps(
                {"errorMessage": f"The resource '{model_name}' already exists."},
                default=str,
            ),
        }
    else:
        ping_id = ping["id"]

    # Create resource
    add_integration_method(
        api_id=api_id,
        resource_id=ping_id,
        rest_method="POST",
        function_name=PROXY_LAMBDA_NAME,
    )

    # upload file to s3
    key = f"{username}/{model_name}"
    try:
        response = s3.upload_file(
            Filename="./ping.py",
            Bucket=MODELS_S3_BUCKET,
            Key=key,
            ExtraArgs={
                "Metadata": {"model-type": "ping"},
                "ContentType": "model/ping",
            },
        )
    except Exception as err:
        print(err)
        try:
            print(json.dumps(response, default=str))
        except:
            pass

    return {
        "isBase64Encoded": False,
        "statusCode": 201,
        # "headers": {"headerName": "headerValue"},
        "body": json.dumps({}, default=str),
    }
