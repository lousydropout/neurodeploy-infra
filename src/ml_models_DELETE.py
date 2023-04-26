import os
import json
from helpers import cors
from helpers import validation
import boto3

PREFIX = os.environ["prefix"]
_REGION_NAME = os.environ["region_name"]
MODELS_S3_BUCKET = f"{PREFIX}-models-{_REGION_NAME}"
LOGS_S3_BUCKET = f"{PREFIX}-logs-{_REGION_NAME}"

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")

# other boto3 clients
apigw = boto3.client("apigateway")
iam = boto3.client("iam")
s3 = boto3.client("s3")


def delete_model(username: str, model_name: str):
    key = f"{username}/{model_name}"

    # try to retrieve metadata about model
    # will raise exception if model does not exist
    s3.head_object(Bucket=MODELS_S3_BUCKET, Key=key)

    # delete model if it exists
    response = s3.delete_object(Bucket=MODELS_S3_BUCKET, Key=key)
    return response


@validation.check_authorization
def handler(event: dict, context):
    username = event["username"]
    model_name = event["path_params"]["proxy"]

    # Delete resource
    try:
        x = delete_model(username, model_name)
    except s3.exceptions.NoSuchKey:
        return cors.get_response(
            status_code=400,
            body={"error_message": f"Model {model_name} does not exist"},
            methods="DELETE",
        )
    except Exception as err:
        print(err)
        return cors.get_response(
            status_code=400,
            body={"error_message": f"Failed to delete model {model_name}"},
            methods="DELETE",
        )
    print(json.dumps(x))

    return cors.get_response(
        status_code=200,
        body={"message": f"deleted model {model_name}"},
        methods="DELETE",
    )
