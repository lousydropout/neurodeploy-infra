import os
from time import time
from datetime import datetime
import json
from hashlib import sha256
from helpers import cors, dynamodb as ddb
from helpers.decimal_encoder import DecimalEncoder
from helpers.logging import logger
import boto3

_PREFIX = os.environ["prefix"]
_REGION_NAME = os.environ["region_name"]
LOGS_S3_BUCKET = f"{_PREFIX}-logs-{_REGION_NAME}"
MODELS_S3_BUCKET = f"{_PREFIX}-models-{_REGION_NAME}"
EXECUTION_LAMBDA_ARN = os.environ["lambda"]
PREPROCESSING_LAMBDA_ARN = os.environ["preprocessing_lambda"]

lambda_ = boto3.client("lambda")
s3 = boto3.client("s3")

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
MODELS_TABLE_NAME = f"{_PREFIX}_Models"
MODELS_TABLE = dynamodb.Table(MODELS_TABLE_NAME)
USAGES_TABLE_NAME = f"{_PREFIX}_Usages"
USAGES_TABLE = dynamodb.Table(USAGES_TABLE_NAME)


def add_to_usages_table(
    status_code: int,
    username: str,
    model_name: str,
    start_time: str,
    location: str,
    duration: int,
    input: str | None,
    output: str | None,
    error: str | None,
):
    try:
        record = {
            "pk": f"{username}|{model_name}",
            "sk": start_time,
            "status_code": status_code,
            "location": location,
            "duration": duration,
            "input": input,
            "output": output,
            "error": error,
        }
        logger.info("add record to dynamodb: %s", json.dumps(record))
        USAGES_TABLE.put_item(Item=record)
    except Exception as err:
        logger.exception(err)


def get_model_info(
    username: str,
    model_name: str,
) -> tuple[dict, dict[str, str]]:
    statement = f"""
    SELECT * FROM {MODELS_TABLE_NAME}
    WHERE pk='username|{username}' AND (CONTAINS("sk", '{model_name}') OR CONTAINS("sk", '*'));
    """
    response = dynamodb_client.execute_statement(Statement=statement)
    results = [ddb.from_(x) for x in response.get("Items", [])]
    logger.debug("get_model_info results: %s", json.dumps(results, default=str))
    if not results:
        raise Exception(f"Unable to locate model '{model_name}'")

    try:
        model_info = next(result for result in results if result["sk"] == model_name)
    except StopIteration:
        model_info = {}

    logger.debug("model_info: %s", json.dumps(model_info, default=str))
    hashed_keys = {
        result["hashed_key"]: result.get("expires_at") or ""
        for result in results
        if result["sk"] != model_name
    }
    logger.debug("hashed_keys: %s", hashed_keys)

    return model_info, hashed_keys


def parse_event(event: dict) -> tuple[bool, dict]:
    headers = event["headers"]
    request_context = event["requestContext"]
    path: str = event["path"].strip("/").strip()
    if path.count("/") != 1:
        logger.error("Something's wrong with path: %s", path)
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


def read_object(bucket: str, key: str) -> str:
    response = s3.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    return body.decode()


def preprocess(username: str, model_name: str, payload: dict) -> dict:
    result, status_code = payload, 200
    # Get source code of preprocessing function
    source = read_object(
        bucket=MODELS_S3_BUCKET,
        key=f"{username}/{model_name}_preprocessing",
    )

    extended_payload = {
        "payload": payload,
        "preprocessing": source,
    }
    # Invoke the preprocessing lambda with the payload
    result, status_code = invoke_lambda(
        function_name=PREPROCESSING_LAMBDA_ARN,
        payload=json.dumps(extended_payload),
    )
    if "error" in result:
        raise Exception(result["error"])

    return result, status_code


def handler(event: dict, context) -> dict:
    logger.debug("Event: %s", json.dumps(event))
    success, parsed_event = parse_event(event)
    if not success:
        logger.info("Invalid input: %s", parsed_event["message"])
        return cors.get_response(
            body={"error": parsed_event["message"]},
            status_code=parsed_event["status_code"],
            headers="*",
            methods="POST",
        )

    start_time = datetime.utcnow().isoformat()
    start = time()
    logger.info("start time: %s, %s", start_time, start)

    # get username and model_name
    path: str = parsed_event["path"]
    logger.info("path: %s", path)
    username, model_name = path.split("/")
    logger.debug("username, model_name: %s, %s", username, model_name)

    # get payload
    body = parsed_event["body"]
    payload = body
    if isinstance(body, dict) and "payload" in body:
        payload = body["payload"] or ""
    logger.debug("payload: %s", payload)

    # Create payload for the execution lambda (and, potentially, preprocessing lambda)
    model_info, hashed_keys = get_model_info(username=username, model_name=model_name)
    logger.info("model_info, hashed_keys: %s, %s", model_info, hashed_keys)
    has_preprocessing = model_info.get("has_preprocessing") or False

    # Validate the user has permission (return error response if there is one, else assume everything's fine)
    error = raises_error(
        model_info=model_info,
        parsed_event=parsed_event,
        hashed_keys=hashed_keys,
    )
    if error:
        logger.error("Error: %s", json.dumps(error, default=str))
        return error

    # Preprocess payload
    preprocessed_payload = payload
    if has_preprocessing:
        preprocessed_payload = preprocess(
            username=username,
            model_name=model_name,
            payload=payload,
        )

    # run program
    output_and_error = {}
    try:
        output_and_error, result = main(
            model_location=path,
            payload=preprocessed_payload,
            model_info=model_info,
        )
    except Exception as err:
        logger.exception("Error at main: %s", err)
        error = str(error)
        output_and_error = {"output": None, "error": error}
        result = cors.get_response(
            body={"error": error},
            status_code=500,
            headers="*",
            methods="POST",
        )

    # get duration
    duration = int((time() - start) * 1000)  # in milliseconds

    # get output and error
    output = output_and_error.get("output")
    error = output_and_error.get("error")

    # save to s3
    location = f"{path.strip('/')}/{start_time}.json"
    s3.put_object(
        Body=json.dumps(
            {
                "username": username,
                "model_name": model_name,
                "status_code": result["statusCode"],
                "start_time": start_time,
                "duration": duration,
                "input": payload,
                "preprocessed_payload": preprocessed_payload,
                "output": output,
                "error": error,
            },
            default=str,
        ),
        Bucket=LOGS_S3_BUCKET,
        Key=location,
    )

    # add to dynamodb
    limit = 10_000  # number of characters for 10kB
    output_string = (
        json.dumps(output, cls=DecimalEncoder, default=str)
        if isinstance(output, list | dict)
        else output
    )
    error_string = (
        json.dumps(error, cls=DecimalEncoder, default=str)
        if isinstance(error, list | dict)
        else error
    )
    add_to_usages_table(
        status_code=result["statusCode"],
        username=username,
        model_name=model_name,
        start_time=start_time,
        duration=duration,
        input=event["body"] if len(event["body"]) < limit else None,
        output=(
            output_string
            if not isinstance(output_string, str) or len(output_string) < limit
            else None
        ),
        error=(
            error_string
            if not isinstance(error_string, str) or len(error_string) < limit
            else None
        ),
        location=location,
    )

    return result


def raises_error(
    model_info: dict,
    parsed_event: dict,
    hashed_keys: dict[str, str],
) -> dict | None:
    # If model does not exist
    if not model_info:
        return cors.get_response(
            body={"error": "ML model is mising. Unable to execute model."},
            status_code=404,
            headers="*",
            methods="POST",
        )

    # If model has yet to be uploaded
    if not model_info["is_uploaded"]:
        return cors.get_response(
            body={
                "error": "ML model has not yet been uploaded. Unable to execute model."
            },
            status_code=404,
            headers="*",
            methods="POST",
        )

    # If the model is marked as "is_deleted"
    if model_info["is_deleted"]:
        return cors.get_response(
            body={"error": "Cannot execute deleted ML model."},
            status_code=400,
            headers="*",
            methods="POST",
        )

    # If model is not public but no api key was provided
    if not model_info["is_public"] and "api-key" not in parsed_event["headers"]:
        return cors.get_response(
            body={"error": "Model is not public but no api key was provided."},
            status_code=403,
            headers="*",
            methods="POST",
        )

    # If model is not public but no api key provided matches
    hashed_value = None
    if not model_info["is_public"]:
        api_key = parsed_event["headers"].get("api-key") or ""
        hashed_value = sha256(api_key.encode()).hexdigest()
        if hashed_value not in hashed_keys:
            logger.debug("hash of key received: %s", hashed_value)
            logger.debug("hashed keys: %s", hashed_keys)
            logger.debug("hashed_value in hashed_keys: %s", hashed_value in hashed_keys)
            return cors.get_response(
                body={"error": "A valid API key is required for this ML model."},
                status_code=403,
                headers="*",
                methods="POST",
            )

    # If model is not public and api key has expired
    current_time = datetime.utcnow().isoformat()
    if (
        not model_info["is_public"]
        and hashed_value in hashed_keys
        and hashed_keys[hashed_value]
        and hashed_keys[hashed_value] < current_time
    ):
        return cors.get_response(
            body={"error": "The API key you provided has already expired."},
            status_code=403,
            headers="*",
            methods="POST",
        )

    logger.info("No error raised")

    return None


def main(model_location: str, payload: str, model_info: dict) -> tuple[dict, dict]:
    lambda_payload = json.dumps(
        {
            "payload": payload,
            "model": model_location,
            "persistence_type": model_info["filetype"],
            "model_type": model_info["library"],
        },
        default=str,
    )
    logger.debug("lambda_payload: %s", lambda_payload)

    # Invoke the execution lambda with the above payload
    result, status_code = invoke_lambda(
        function_name=EXECUTION_LAMBDA_ARN,
        payload=lambda_payload,
    )

    # Parse and return result
    return result, cors.get_response(
        body=result,
        status_code=status_code,
        headers="*",
        methods="POST",
    )


def invoke_lambda(function_name: str, payload: str):
    try:
        lambda_response = lambda_.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=payload,
        )
    except lambda_.exceptions.TooManyRequestsException as err:
        logger.exception("TooManyRequestsException: %s", err)
        status_code, result = 429, {"error": "Too Many Requests"}
    except Exception as err:
        logger.exception("Exception: %s", err)
        status_code, result = 400, {"error": str(err)}
    else:
        response = lambda_response["Payload"].read().decode()
        logger.info("Response: %s", response)
        response_dict = json.loads(response)

        if "output" in response_dict:
            status_code = 200
            result = {"output": response_dict["output"]}
        else:
            status_code = 400
            result = {"error": response_dict["error"]}

    return result, status_code
