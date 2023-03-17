import os
import json
from datetime import datetime
from helpers import validation
import boto3

_REGION_NAME = os.environ["region_name"]
MODELS_S3_BUCKET = f"neurodeploy-models-{_REGION_NAME}"

s3 = boto3.client("s3")


def get_model_info(item: dict) -> dict:
    model_name = item["Key"]
    res = s3.head_object(Bucket=MODELS_S3_BUCKET, Key=model_name)
    updated_at: datetime = item["LastModified"]
    return {
        "model_name": model_name.split("/")[1],
        "model_type": res["Metadata"]["model-type"],
        "persistence_type": res["ContentType"].split("/")[1],
        "uploaded_at": updated_at.isoformat(),
    }


def get_models(username: str) -> list[dict]:
    response = s3.list_object_versions(Bucket=MODELS_S3_BUCKET, Prefix=username)
    return [get_model_info(item) for item in response["Versions"] if item["IsLatest"]]


@validation.check_authorization
def handler(event: dict, context):
    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": json.dumps(
            {"models": get_models(event["username"])},
            default=str,
        ),
    }
