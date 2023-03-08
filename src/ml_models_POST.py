import os
import json
from helpers import dynamodb as ddb
from helpers import validation
import boto3
from botocore.exceptions import ClientError

_ACCOUNT_NUMBER = os.environ["account_number"]
_REGION_NAME = os.environ["region_name"]
PROXY_LAMBDA_ARN = os.environ["proxy_arn"]
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


def get_record(username: str, table_name: str) -> dict:
    key = ddb.to_({"pk": username, "sk": _REGION_NAME})
    response = dynamodb_client.get_item(TableName=table_name, Key=key)
    return ddb.from_(response.get("Item", {}))


def get_api_record(username: str) -> dict:
    return get_record(username, _APIS_TABLE_NAME)


def get_model_record(username: str) -> dict:
    return get_record(username, _MODELS_TABLE_NAME)


def write_api_object(username: str, payload: dict):
    record = {"pk": username, "sk": _REGION_NAME, **payload}
    _API_TABLE.put_item(Item=record)


def write_model_object(username: str, model: str, sk: str, payload: dict):
    record = {"pk": f"{username}|{model}", "sk": sk, **payload}
    _MODEL_TABLE.put_item(Item=record)


#
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
    deployment = apigw.create_deployment(
        restApiId=api_id,
        stageName="prod",
        tracingEnabled=False,
    )


@validation.check_authorization
def handler(event: dict, context):
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
        function_name=PROXY_LAMBDA_ARN,
    )

    # write model to dynamodb
    payload = {"type": "PING", "location": None}
    write_model_object(username=username, model=model_name, sk="ping", payload=payload)
    write_model_object(username=username, model=model_name, sk="main", payload=payload)

    # create presigned url for model
    key = f"{username}/{model_name}"
    response = s3.generate_presigned_post(Bucket=MODELS_S3_BUCKET, Key=key)
    print("Response: ", json.dumps(response))

    # # Demonstrate how another Python program can use the presigned URL to upload a file
    # with open(object_name, 'rb') as f:
    #     files = {'file': (object_name, f)}
    #     http_response = requests.post(response['url'], data=response['fields'], files=files)
    # # If successful, returns HTTP status code 204
    # logging.info(f'File upload HTTP status code: {http_response.status_code}')

    return {
        "isBase64Encoded": False,
        "statusCode": 201,
        # "headers": {"headerName": "headerValue"},
        "body": json.dumps(response, default=str),
    }
