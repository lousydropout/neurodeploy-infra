from typing import Tuple, Union
import os
import json
from hashlib import sha256
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
    statement = f"""
    SELECT * FROM {MODELS_TABLE_NAME}
    WHERE pk='username|{username}' AND (CONTAINS("sk", '{model_name}') OR CONTAINS("sk", '*'));
    """
    response = dynamodb_client.execute_statement(Statement=statement)
    results = [ddb.from_(x) for x in response.get("Items", [])]
    print("get_model_info results: ", json.dumps(results, default=str))
    if not results:
        raise Exception(f"Unable to locate model '{model_name}'")

    model_info = next(result for result in results if result["sk"] == model_name)
    hashed_keys = set(
        result["hashed_key"] for result in results if result["sk"] != model_name
    )

    return model_info, hashed_keys


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


def raises_error(
    model_info: dict,
    parsed_event: dict,
    hashed_keys: set,
) -> Union[dict, None]:
    # If model has yet to be uploaded,
    if not model_info["is_uploaded"]:
        return cors.get_response(
            body={"error": "ML model is mising. Unable to execute model."},
            status_code=500,
            headers="*",
            methods="POST",
        )

    # If the model is marked as "deleted"
    if model_info["is_deleted"]:
        return cors.get_response(
            body={"error": "Cannot execute deleted ML model."},
            status_code=500,
            headers="*",
            methods="POST",
        )

    # If model is not public but no api key was provided
    if not model_info["is_public"] and "api-key" not in parsed_event["headers"]:
        return cors.get_response(
            body={"error": "A valid API key is required for this ML model."},
            status_code=403,
            headers="*",
            methods="POST",
        )

    # If model is not public but no api key provided matches
    api_key = parsed_event["headers"]["api-key"]
    hashed_value = sha256(api_key.encode()).hexdigest()
    if not model_info["is_public"] and hashed_value not in hashed_keys:
        return cors.get_response(
            body={"error": "A valid API key is required for this ML model."},
            status_code=403,
            headers="*",
            methods="POST",
        )

    return None


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
    username, model_name = model_location.strip().strip("/").split("/")

    # Create payload for the execution lambda
    model_info, hashed_keys = get_model_info(username=username, model_name=model_name)
    print("model_info: ", model_info)
    print("hashed_keys: ", hashed_keys)

    # Validate the user has permission (return error response if there is one, else assume everything's fine)
    error = raises_error(
        model_info=model_info, parsed_event=parsed_event, hashed_keys=hashed_keys
    )
    if error:
        return error

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
        status_code, result = 429, {"error": "Too Many Requests"}
    except Exception as err:
        print(err)
        status_code, result = 400, {"error": str(err)}
    else:
        status_code = 200
        response = lambda_response["Payload"].read().decode()
        print("Result: ", response)
        result = {"output": json.loads(response)["output"]}

    # Parse and return result
    return cors.get_response(
        body=result,
        status_code=status_code,
        headers="*",
        methods="POST",
    )
