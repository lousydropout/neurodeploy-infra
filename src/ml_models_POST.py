import os
from uuid import uuid4 as uuid
from datetime import datetime
import string
import json
from helpers import cors, validation
import boto3
from botocore.exceptions import ClientError

_PREFIX = os.environ["prefix"]
_REGION_NAME = os.environ["region_name"]
MODELS_S3_BUCKET = f"{_PREFIX}-models-{_REGION_NAME}"
STAGING_S3_BUCKET = f"{_PREFIX}-staging-{_REGION_NAME}"
MODELS_TABLE_NAME = f"{_PREFIX}_Models"

apigw = boto3.client("apigateway")
s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
MODELS_TABLE = dynamodb.Table(MODELS_TABLE_NAME)


def upsert_ml_model_record(
    username: str,
    model_name: str,
    lib_type: str,
    filetype: str,
    bucket: str,
    key: str,
    is_public: bool = False,
):
    record = {
        "pk": f"username|{username}",
        "sk": model_name,
        "library": lib_type,
        "filetype": filetype,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "deleted_at": None,
        "uploaded": False,
        "deleted": False,
        "bucket": bucket,
        "key": key,
        "is_public": is_public,
    }
    MODELS_TABLE.put_item(Item=record)


# def get_api_id(username: str) -> str:
#     key = ddb.to_({"pk": username, "sk": "resources"})
#     response = dynamodb.get_item(TableName=_APIS_TABLE_NAME, Key=key)
#     return ddb.from_(response.get("Item", {"api_id": None}))["api_id"]


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


LIB_TYPE = {"tensorflow", "scikit-learn"}
FILETYPES = {"h5", "joblib", "pickle"}

MODEL_FILETYPES = {
    ("tensorflow", "h5"),
    ("scikit-learn", "joblib"),
    ("scikit-learn", "pickle"),
}


def validate_params(
    username: str,
    lib_type: str,
    filetype: str,
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

    # validate lib_type value
    if not lib_type:
        errors.append(f"Missing param: 'lib' must be one of { LIB_TYPE }")
    elif lib_type not in LIB_TYPE:
        errors.append(
            f"Invalid value for param 'lib': 'lib' must be one of { LIB_TYPE }"
        )

    # validate filetype value
    if not filetype:
        errors.append(f"Missing param: 'filetype' must be one of { FILETYPES }")
    elif filetype not in FILETYPES:
        errors.append(
            f"Invalid value for param 'filetype': 'filetype' must be one of { FILETYPES }"
        )

    # validate (lib_type, filetype) pair
    if (lib_type, filetype) not in MODEL_FILETYPES:
        errors.append(
            f"Invalid (lib, filetype) pair: (lib, filetype) must be one of { MODEL_FILETYPES }"
        )

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
    username = event["username"]

    body = json.loads(event["body"])
    query_params = event["query_params"]
    print("body, query_params: ", body, query_params)
    params = {**body, **query_params}  # query params take precedence
    print("params: ", params)

    lib_type = params.get("lib")
    filetype = params.get("filetype")
    _is_public = params.get("is_public")
    is_public = (
        bool(_is_public)
        if _is_public and _is_public.lower() in ("true", "false")
        else False
    )

    path_params = event["path_params"]
    model_name = path_params["model_name"]

    # validate params
    errors = validate_params(
        username=username,
        lib_type=lib_type,
        filetype=filetype,
        model_name=model_name,
    )

    # return error message if errors
    if errors:
        return cors.get_response(
            status_code=400, body={"errors": errors}, methods="PUT"
        )

    # create record in db
    upsert_ml_model_record(
        username=username,
        model_name=model_name,
        lib_type=lib_type,
        filetype=filetype,
        bucket=None,
        key=None,
        is_public=is_public,
    )

    # Create presigned post
    response = create_presigned_post(
        bucket_name=STAGING_S3_BUCKET,
        object_name=str(uuid()),
        fields={
            "x-amz-meta-username": username,
            "x-amz-meta-model_name": model_name,
            "x-amz-meta-lib": lib_type,
            "x-amz-meta-filetype": filetype,
            "Content-Type": f"model/{filetype}",
        },
        conditions=[
            {"x-amz-meta-username": username},
            {"x-amz-meta-model_name": model_name},
            {"x-amz-meta-lib": lib_type},
            {"x-amz-meta-filetype": filetype},
            {"Content-Type": f"model/{filetype}"},
        ],
    )
    print("Response: ", json.dumps(response))

    return cors.get_response(
        status_code=201,
        body={
            "message": f"Please upload your {lib_type} {filetype} model to complete the process.",
            **response,
        },
        methods="PUT",
    )
