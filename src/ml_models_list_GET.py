import os
from datetime import datetime
from helpers import cors, validation
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
    return [
        get_model_info(item)
        for item in response.get("Versions", [])
        if item.get("IsLatest", False)
    ]


@validation.check_authorization
def handler(event: dict, context):
    try:
        results = get_models(event["username"])
    except:
        results = []

    return cors.get_response(status_code=200, body={"models": results}, methods="GET")
