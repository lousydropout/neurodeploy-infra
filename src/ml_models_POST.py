import os
from uuid import uuid4 as uuid
import json
from helpers import dynamodb as ddb
from helpers import validation
import boto3
from botocore.exceptions import ClientError

_REGION_NAME = os.environ["region_name"]
PROXY_LAMBDA_ARN = os.environ["proxy_arn"]
PING_LAMBDA_ROLE = os.environ["ping_role"]

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


def get_record(username: str, table_name: str) -> dict:
    key = ddb.to_({"pk": username, "sk": _REGION_NAME})
    response = dynamodb_client.get_item(TableName=table_name, Key=key)
    return ddb.from_(response.get("Item", {}))


def get_api_record(username: str) -> dict:
    return get_record(username, _APIS_TABLE_NAME)


def get_model_record(username: str) -> dict:
    return get_record(username, _MODELS_TABLE_NAME)


#
def add_integration_method(
    api_id: str,
    resource_id: str,
    rest_method: str,
    service_endpoint_prefix: str,
    service_action: str,
    service_method: str,
    role_arn: str,
    mapping_template: dict,
):
    """
    Adds an integration method to a REST API. An integration method is a REST
    resource, such as '/users', and an HTTP verb, such as GET. The integration
    method is backed by an AWS service, such as Amazon DynamoDB.
    :param resource_id: The ID of the REST resource.
    :param rest_method: The HTTP verb used with the REST resource.
    :param service_endpoint_prefix: The service endpoint that is integrated with
                                    this method, such as 'dynamodb'.
    :param service_action: The action that is called on the service, such as
                            'GetItem'.
    :param service_method: The HTTP method of the service request, such as POST.
    :param role_arn: The Amazon Resource Name (ARN) of a role that grants API
                        Gateway permission to use the specified action with the
                        service.
    :param mapping_template: A mapping template that is used to translate REST
                                elements, such as query parameters, to the request
                                body format required by the service.
    """
    service_uri = (
        f"arn:aws:apigateway:{_REGION_NAME}"
        f":{service_endpoint_prefix}:action/{service_action}"
    )
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

    try:
        apigw.put_integration(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod=rest_method,
            type="AWS",
            integrationHttpMethod=service_method,
            credentials=role_arn,
            requestTemplates={"application/json": json.dumps(mapping_template)},
            uri=service_uri,
            passthroughBehavior="WHEN_NO_TEMPLATES",
        )
        apigw.put_integration_response(
            restApiId=api_id,
            resourceId=resource_id,
            httpMethod=rest_method,
            statusCode="200",
            responseTemplates={"application/json": ""},
        )
        print(
            "Created integration for resource %s to service URI %s.",
            resource_id,
            service_uri,
        )
    except ClientError:
        print(
            "Couldn't create integration for resource %s to service URI %s.",
            resource_id,
            service_uri,
        )
        raise


def create_iam_role(role_name: str):
    response = iam.create_role(
        Path=f"/",
        RoleName=f"{role_name}-{uuid().hex}",
        AssumeRolePolicyDocument="string",
        Description="string",
        MaxSessionDuration=123,
        PermissionsBoundary="string",
        Tags=[
            {"Key": "string", "Value": "string"},
        ],
    )


def create_something(api_id: str, root_id: str, resource_name: str):
    ping = apigw.create_resource(
        restApiId=api_id,
        parentId=root_id,
        pathPart=resource_name,
    )
    ping_id = ping["id"]

    role = boto3.resource("iam").Role(role_name)

    add_integration_method(
        api_id=api_id,
        resource_id=ping_id,
        rest_method="POST",
        service_endpoint_prefix="lambda",
        service_action="InvokeFunction",
        service_method="POST",
    )

    # # 6. create method (requires resource)
    # GET_ping = apigw.put_method(
    #     restApiId=api_id,
    #     resourceId=ping_id,
    #     httpMethod="POST",
    #     authorizationType="NONE",
    # )

    # # 7. create integration
    # ping_integration = apigw.put_integration(
    #     restApiId=api_id,
    #     resourceId=ping_id,
    #     httpMethod="POST",
    #     integrationHttpMethod="PUT",
    #     type="AWS_PROXY",
    # )

    # # 8. create integration response
    # POST_ping_response = apigw.put_integration_response(
    #     restApiId=api_id,
    #     resourceId=ping_id,
    #     httpMethod="POST",
    #     statusCode="200",
    #     responseTemplates={},
    # )

    # # 9. create method response
    # ping_method_response = apigw.put_method_response(
    #     restApiId=api_id,
    #     resourceId=ping_id,
    #     httpMethod="POST",
    #     statusCode="200",
    # )

    # # 10. create deployment (apigw mush contain method)
    # deployment = apigw.create_deployment(
    #     restApiId=api_id,
    #     stageName="prod",
    #     tracingEnabled=False,
    # )


@validation.check_authorization
def handler(event: dict, context):
    jwt_payload = event["jwt_payload"]
    username = jwt_payload["username"]

    api_record = get_api_record(username)
    resources = api_record["resources"]
    api_id = resources["rest_api_id"]
    root_id = resources["root_id"]
    domain_name = resources["domain_name"]

    #

    return {
        "isBase64Encoded": False,
        "statusCode": 201,
        "headers": {"headerName": "headerValue"},
        "body": json.dumps({}, default=str),
    }
