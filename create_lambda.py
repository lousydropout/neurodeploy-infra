import json
import boto3

apigw = boto3.client("apigateway")
iam = boto3.client("iam")
lambda_ = boto3.client("lambda")
s3 = boto3.client("s3")


# IAM Policies
_AWSLambdaRole = "arn:aws:iam::aws:policy/service-role/AWSLambdaRole"
_AWSLambdaDynamoDB = "arn:aws:iam::aws:policy/AWSLambdaInvocation-DynamoDB"

api_id = "gk35c1fpx0"
response = apigw.get_rest_api(restApiId=api_id)

root_id = "94ld6f44kb"
response = apigw.get_resource(restApiId=api_id, resourceId=root_id)

# create resource
resource_name = "model1"
model1 = apigw.create_resource(
    restApiId=api_id,
    parentId=root_id,
    pathPart="model1",
)
model1_id = model1["id"]

# create method
POST_model1 = apigw.put_method(
    restApiId=api_id,
    resourceId=model1_id,
    httpMethod="POST",
    authorizationType="NONE",
)

apigw.put_method_response(
    restApiId=api_id,
    resourceId=model1_id,
    httpMethod="POST",
    statusCode="200",
    responseModels={"application/json": "Empty"},
)

# # integration


def create_lamdba_function(name: str):
    func = lambda_.create_function(
        FunctionName=name,
        Runtime="python3.9",
        Role="string",
        Handler="proxy.handler",
        Timeout=30,
        MemorySize=128,
        Code="",
    )
