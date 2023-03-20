import os
import json
from datetime import datetime
from helpers import validation
import boto3

_REGION_NAME = os.environ["region_name"]
MODELS_S3_BUCKET = f"neurodeploy-models-{_REGION_NAME}"

s3 = boto3.client("s3")


def get_model_info(username: str, model_name: str) -> dict:
    key = f"{username}/{model_name}"
    res = s3.head_object(Bucket=MODELS_S3_BUCKET, Key=key)
    updated_at: datetime = res["LastModified"]
    return {
        "model_name": model_name,
        "model_type": res["Metadata"]["model-type"],
        "persistence_type": res["ContentType"].split("/")[1],
        "uploaded_at": updated_at.isoformat(),
    }


@validation.check_authorization
def handler(event: dict, context):
    username = event["username"]
    path_params = event["path_params"]
    model_name = path_params["proxy"]
    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",  # Required for CORS support to work
            "Access-Control-Allow-Credentials": True,  # Required for cookies, authorization headers with HTTPS
            "Access-Control-Allow-Methods": "GET",  # Allow only GET request
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(
            get_model_info(username=username, model_name=model_name),
            default=str,
        ),
    }
