import os
from datetime import datetime
from helpers import cors
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

    return cors.get_response(
        status_code=200,
        body=get_model_info(username=username, model_name=model_name),
        methods="GET",
    )
