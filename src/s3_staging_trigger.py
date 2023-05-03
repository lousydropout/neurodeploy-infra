import os
from datetime import datetime
import json
from collections import namedtuple
import boto3
from helpers import dynamodb as ddb

s3_tuple = namedtuple("s3_tuple", ["bucket", "key"])

s3 = boto3.client("s3")
s3r = boto3.resource("s3")

_PREFIX = os.environ["prefix"]


# dynamodb boto3
MODELS_TABLE_NAME = f"{_PREFIX}_Models"
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
MODELS_TABLE = dynamodb.Table(MODELS_TABLE_NAME)


def get_model(username: str, model_name: str) -> dict:
    statement = f"SELECT * FROM {MODELS_TABLE_NAME} WHERE pk='username|{username}' AND sk='{model_name}';"
    response = dynamodb_client.execute_statement(Statement=statement)
    return ddb.from_(response.get("Items", [{}])[0])


def upsert_ml_model_record(
    username: str,
    model_name: str,
    lib_type: str,
    filetype: str,
    bucket: str,
    key: str,
    is_public: bool = False,
):
    record = get_model(username=username, model_name=model_name)
    record.update(
        {
            "updated_at": datetime.utcnow().isoformat(),
            "is_uploaded": True,
            "bucket": bucket,
            "key": key,
        }
    )
    MODELS_TABLE.put_item(Item=record)


def get_attributes(bucket_name: str, object_name: str) -> dict:
    try:
        response = s3.get_object(Bucket=bucket_name, Key=object_name)
    except s3.exceptions.NoSuchKey:
        raise Exception("The resource you requested does not exist.")

    return response["Metadata"]


def handler(event: dict, context):
    print("Event: ", json.dumps(event))

    for record in event["Records"]:
        try:
            main(record)
        except Exception as err:
            print("Error: ", json.dumps({"event": record, "error": err}, default=str))


def move_object(from_: s3_tuple, to_: s3_tuple):
    # Copy object A as object B
    copy_source = {"Bucket": from_.bucket, "Key": from_.key}
    bucket = s3r.Bucket(to_.bucket)
    bucket.copy(copy_source, to_.key)

    # Delete the former object A
    s3r.Object(from_.bucket, from_.key).delete()


def main(event: dict):
    _REGION_NAME = event["awsRegion"]
    MODELS_S3_BUCKET = f"{_PREFIX}-models-{_REGION_NAME}"

    s3_bucket = event["s3"]["bucket"]["name"]
    s3_object = event["s3"]["object"]["key"]

    # get metadata
    s3_metadata = get_attributes(bucket_name=s3_bucket, object_name=s3_object)
    print("s3_metadata: ", json.dumps(s3_metadata, default=str))

    # move object
    s3_key = f"{s3_metadata['username']}/{s3_metadata['model_name']}"
    from_ = s3_tuple(s3_bucket, s3_object)
    to_ = s3_tuple(MODELS_S3_BUCKET, s3_key)
    move_object(from_=from_, to_=to_)

    # update db
    upsert_ml_model_record(
        username=s3_metadata["username"],
        model_name=s3_metadata["model_name"],
        lib_type=s3_metadata["lib"],
        filetype=s3_metadata["filetype"],
        bucket=s3_bucket,
        key=s3_key,
    )
