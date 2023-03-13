import os
import string
import json
from helpers import dynamodb as ddb
from helpers import validation
import boto3
from botocore.exceptions import ClientError

_REGION_NAME = os.environ["region_name"]
MODELS_S3_BUCKET = f"neurodeploy-models-{_REGION_NAME}"


apigw = boto3.client("apigateway")
s3 = boto3.client("s3")
dynamodb = boto3.client("dynamodb")
_APIS_TABLE_NAME = "neurodeploy_Apis"


def get_api_id(username: str) -> str:
    key = ddb.to_({"pk": username, "sk": "resources"})
    response = dynamodb.get_item(TableName=_APIS_TABLE_NAME, Key=key)
    return ddb.from_(response.get("Item", {"api_id": None}))["api_id"]


def create_presigned_post(
    bucket_name: str,
    object_name: str,
    fields: dict,
    conditions: list,
    expiration=3600,
):
    # Generate a presigned S3 POST URL
    s3_client = boto3.client("s3")
    try:
        response = s3_client.generate_presigned_post(
            Bucket=bucket_name,
            Key=object_name,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=expiration,
        )
    except ClientError as err:
        print(err)
        raise err

    # The response contains the presigned URL and required fields
    return response


MODEL_TYPES = {
    "tensorflow",
}
PERSISTENCE_TYPES = {"h5"}

MODEL_PERSISTENCE_TYPES = {("tensorflow", "h5")}


def validate_params(
    username: str,
    model_type: str,
    persistence_type: str,
    model_name: str,
) -> list[str]:
    errors = []

    # confirm that the model has already been created
    # api_id = get_api_id(username)
    # response = apigw.get_resources(restApiId=api_id)
    # exists = any(y for y in response["items"] if y.get("pathPart", "") == model_name)
    # if not exists:
    #     # TODO: Just create the model for them here
    #     errors.append(f"Model '{model_name}' has not been created yet.")

    # validate model_type value
    if not model_type:
        errors.append(f"Missing param: 'model_type' must be one of { MODEL_TYPES }")
    elif model_type not in MODEL_TYPES:
        errors.append(
            f"Invalid value for param 'model_type': 'model_type' must be one of { MODEL_TYPES }"
        )

    # validate persistence_type value
    if not persistence_type:
        errors.append(
            f"Missing param: 'persistence_type' must be one of { PERSISTENCE_TYPES }"
        )
    elif persistence_type not in PERSISTENCE_TYPES:
        errors.append(
            f"Invalid value for param 'persistence_type': 'persistence_type' must be one of { PERSISTENCE_TYPES }"
        )

    # validate (model_type, persistence_type) pair
    if (model_type, persistence_type) not in MODEL_PERSISTENCE_TYPES:
        errors.append("Invalid (model_type, persistence_type) pair")

    # validate model_name
    remaining = set(model_name).difference(
        set(string.ascii_letters + string.digits + "-_")
    )
    if remaining:
        errors.append(
            "Invalid model name: Only alphanumeric characters [A-Za-z0-9], hyphens ('-'), and underscores ('_') are allowed."
        )

    return errors


@validation.check_authorization
def handler(event: dict, context) -> dict:
    jwt_payload = event["jwt_payload"]
    username = jwt_payload["username"]

    body = json.loads(event["body"])
    query_params = event["query_params"]
    print("body, query_params: ", body, query_params)
    params = {**body, **query_params}  # query params take precedence
    print("params: ", params)

    model_type = params.get("model_type")
    persistence_type = params.get("persistence_type")

    path_params = event["path_params"]
    model_name = path_params["proxy"]

    # validate params
    errors = validate_params(
        username=username,
        model_type=model_type,
        persistence_type=persistence_type,
        model_name=model_name,
    )

    # return error message if errors
    if errors:
        return {
            "isBase64Encoded": False,
            "statusCode": 400,
            "body": json.dumps({"errors": errors}),
        }

    # Create presigned post
    key = f"{username}/{model_name}"
    response = create_presigned_post(
        bucket_name=MODELS_S3_BUCKET,
        object_name=key,
        fields={
            "x-amz-meta-model-type": model_type,
            "Content-Type": f"model/{persistence_type}",
        },
        conditions=[
            {"x-amz-meta-model-type": model_type},
            {"Content-Type": f"model/{persistence_type}"},
        ],
    )
    print("Response: ", json.dumps(response))

    return {
        "isBase64Encoded": False,
        "statusCode": 201,
        # "headers": {"headerName": "headerValue"},
        "body": json.dumps(
            {
                "message": f"Please upload your {model_type} {persistence_type} model to complete the process.",
                **response,
            },
            default=str,
        ),
    }
