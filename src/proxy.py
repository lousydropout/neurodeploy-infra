import os
import json
import boto3

_MODEL_TYPE = "model/"
_MODEL_TYPE_LENGTH = len(_MODEL_TYPE)
_PING = "ping"

PREFIX = os.environ["prefix"]
_REGION_NAME = os.environ["region_name"]
MODELS_S3_BUCKET = f"{PREFIX}-models-{_REGION_NAME}"
EXECUTION_LAMBDA_ARN = os.environ["lambda"]


lambda_ = boto3.client("lambda")
s3 = boto3.client("s3")


def get_attributes(object_name: str) -> dict:
    try:
        response = s3.get_object(Bucket=MODELS_S3_BUCKET, Key=object_name)
    except s3.exceptions.NoSuchKey:
        raise Exception("The resource you requested does not exist.")

    # parse response
    metadata = response["Metadata"]
    content_type = response["ContentType"]
    last_modified = response["LastModified"]
    # last_modified_timestamp = last_modified.isoformat()
    model_type = metadata.get("model-type") or "missing"
    persistence_type = (
        content_type[_MODEL_TYPE_LENGTH:]
        if content_type.startswith(_MODEL_TYPE)
        else "missing"
    )

    return {
        "model_type": model_type,
        "persistence_type": persistence_type,
        "last_modified": last_modified,
    }


def parse_event(event: dict) -> tuple[bool, dict]:
    headers = event["headers"]
    request_context = event["requestContext"]
    path: str = event["path"].lstrip("/")
    if len(path.split("/")) != 2:
        return False, {
            "status_code": 404,
            "message": "The resource you requested does not exist.",
        }

    try:
        body = json.loads(event["body"])
    except:
        return False, {
            "status_code": 400,
            "message": "Error parsing payload. Please make sure that the request body is a JSON string.",
        }

    parsed_event = {
        "http_method": event["httpMethod"],
        "path": path,
        "headers": headers,
        "body": body,
        "query_params": event["queryStringParameters"],
        "path_params": event["pathParameters"],
        "identity": request_context["identity"],
        "request_epoch_time": request_context["requestTimeEpoch"],
    }

    return True, parsed_event


def handler(event: dict, context) -> dict:
    print("Event: ", json.dumps(event))
    success, parsed_event = parse_event(event)
    if not success:
        return {
            "isBase64Encoded": False,
            "statusCode": parsed_event["status_code"],
            "headers": {
                "Access-Control-Allow-Origin": "*",  # Required for CORS support to work
                "Access-Control-Allow-Credentials": True,  # Required for cookies, authorization headers with HTTPS
                "Access-Control-Allow-Methods": "POST",  # Allow only GET request
                "Access-Control-Allow-Headers": "Content-Type",
            },
            "body": json.dumps({"error_message": parsed_event["message"]}, default=str),
        }

    # Further parse event
    model_location = parsed_event["path"]
    body = parsed_event["body"]
    payload = body
    if isinstance(body, dict) and "payload" in body:
        payload = body["payload"] or ""
    print("model_location: ", model_location)
    print("payload: ", payload)

    # Get information from the s3 object's metadata
    try:
        model_attributes = get_attributes(object_name=model_location)
    except Exception as err:
        return {
            "isBase64Encoded": False,
            "statusCode": 404,
            "headers": {
                "Access-Control-Allow-Origin": "*",  # Required for CORS support to work
                "Access-Control-Allow-Credentials": True,  # Required for cookies, authorization headers with HTTPS
                "Access-Control-Allow-Methods": "POST",  # Allow only GET request
                "Access-Control-Allow-Headers": "Content-Type",
            },
            "body": json.dumps({"error_message": str(err)}, default=str),
        }

    print("model_attributes: ", json.dumps(model_attributes, default=str))

    # If model is the initial PING, return "ok"
    if model_attributes["model_type"] == _PING:
        return {"isBase64Encoded": False, "statusCode": 200, "body": "ok"}

    # Create payload for the execution lambda
    lambda_payload = json.dumps(
        {
            "payload": payload,
            "model": model_location,
            "persistence_type": model_attributes["persistence_type"],
            "model_type": model_attributes["model_type"],
        },
        default=str,
    )
    print("lambda_payload: ", lambda_payload)

    # Invoke the execution lambda with the above payload
    try:
        lambda_response = lambda_.invoke(
            FunctionName=EXECUTION_LAMBDA_ARN,
            InvocationType="RequestResponse",
            Payload=lambda_payload,
        )
    except lambda_.exceptions.TooManyRequestsException as err:
        print(err)
        status_code, result = 429, "Too Many Requests"
    except Exception as err:
        print(err)
        status_code, result = 400, "Too Many Requests"
    else:
        status_code = 200
        response = lambda_response["Payload"].read().decode()

    print("Result: ", response)
    result = json.loads(response)

    # Parse and return result
    return {
        "isBase64Encoded": False,
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",  # Required for CORS support to work
            "Access-Control-Allow-Credentials": True,  # Required for cookies, authorization headers with HTTPS
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps({"output": result["output"]}, default=str),
    }
