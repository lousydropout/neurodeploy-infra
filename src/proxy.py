import os
import json
from helpers import dynamodb as ddb
import boto3

_PREFIX = os.environ["prefix"]
_REGION_NAME = os.environ["region_name"]
MODELS_S3_BUCKET = f"{_PREFIX}-models-{_REGION_NAME}"
EXECUTION_LAMBDA_ARN = os.environ["lambda"]


lambda_ = boto3.client("lambda")
s3 = boto3.client("s3")

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
MODELS_TABLE_NAME = f"{_PREFIX}_Models"
MODELS_TABLE = dynamodb.Table(MODELS_TABLE_NAME)


def get_model_info(username: str, model_name: str) -> dict:
    statement = f"SELECT * FROM {MODELS_TABLE_NAME} WHERE pk='username|{username}' AND sk='{model_name}';"
    response = dynamodb_client.execute_statement(Statement=statement)
    return ddb.from_(response.get("Items", [{}])[0])


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
                "Access-Control-Allow-Methods": "POST",  # Allow only POST request
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
    username, model_name = model_location.strip("/").split("/")

    # Create payload for the execution lambda
    model_info = get_model_info(username=username, model_name=model_name)
    # If model has yet to be uploaded,
    if not model_info["uploaded"]:
        return {
            "isBase64Encoded": False,
            "statusCode": 500,
            "body": "ML model is mising. Unable to execute model.",
        }

    lambda_payload = json.dumps(
        {
            "payload": payload,
            "model": model_location,
            "persistence_type": model_info["filetype"],
            "model_type": model_info["library"],
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
        status_code, result = 400, str(err)
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
