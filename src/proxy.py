import os
import json
from helpers import cors, dynamodb as ddb
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


def get_model_info(username: str, model_name: str) -> tuple[dict, set[str]]:
    statement = f"SELECT * FROM {MODELS_TABLE_NAME} WHERE pk='username|{username}' AND sk >= '{model_name}' ORDER BY sk;"
    response = dynamodb_client.execute_statement(Statement=statement)
    results = [ddb.from_(x) for x in response.get("Items", [])]
    print("get_model_info results: ", json.dumps(results, default=str))
    if not results:
        raise Exception(f"Unable to locate model '{model_name}'")

    model_info = results[0]
    api_keys = set((x["api_key"] for x in results[1:]))

    return model_info, api_keys


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
    try:
        return main(event)
    except Exception as err:
        print("Error at main: ", err)
        return cors.get_response(
            body={"error": str(err)},
            status_code=500,
            headers="*",
            methods="POST",
        )


def main(event: dict) -> dict:
    print("Event: ", json.dumps(event))
    success, parsed_event = parse_event(event)
    if not success:
        return cors.get_response(
            body={"error": parsed_event["message"]},
            status_code=parsed_event["status_code"],
            headers="*",
            methods="POST",
        )

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
    model_info, api_keys = get_model_info(username=username, model_name=model_name)
    print("model_info: ", model_info)
    print("api_keys: ", api_keys)
    # If model has yet to be uploaded,
    if not model_info["uploaded"]:
        return cors.get_response(
            body={"error": "ML model is mising. Unable to execute model."},
            status_code=500,
            headers="*",
            methods="POST",
        )

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
    return cors.get_response(
        body={"output": result["output"]},
        status_code=status_code,
        headers="*",
        methods="POST",
    )
