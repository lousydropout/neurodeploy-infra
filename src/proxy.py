import os
import json
from helpers import dynamodb as ddb
import boto3

_REGION_NAME = os.environ["region_name"]
EXECUTION_LAMBDA_ARN = os.environ["lambda"]

lambda_ = boto3.client("lambda")
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
_MODELS_TABLE_NAME = "neurodeploy_Models"
# _MODEL_TABLE = dynamodb.Table(_MODELS_TABLE_NAME)


_PING = "PING"


def get_model_record(username: str, model: str, sk: str) -> dict:
    key = ddb.to_({"pk": f"{username}|{model}", "sk": sk})
    response = dynamodb_client.get_item(TableName=_MODELS_TABLE_NAME, Key=key)
    return ddb.from_(response.get("Item", {}))


def parse_event(event: dict) -> dict:
    headers = event["headers"]
    request_context = event["requestContext"]

    parsed_event = {
        "http_method": event["httpMethod"],
        "path": event["path"],
        "headers": headers,
        "body": json.loads(event["body"]),
        "query_params": event["queryStringParameters"],
        "identity": request_context["identity"],
        "request_epoch_time": request_context["requestTimeEpoch"],
    }

    return parsed_event


def handler(event: dict, context) -> dict:
    print("Event: ", json.dumps(event))
    try:
        parsed_event = parse_event(event)
    except Exception as err:
        print(err)
        return {
            "isBase64Encoded": False,
            "statusCode": 400,
            "headers": {
                "Access-Control-Allow-Origin": "*",  # Required for CORS support to work
                "Access-Control-Allow-Credentials": True,  # Required for cookies, authorization headers with HTTPS
                "Access-Control-Allow-Methods": "POST",  # Allow only GET request
                "Access-Control-Allow-Headers": "Content-Type",
            },
            "body": json.dumps(
                {
                    "error_message": "Error parsing payload. Please make sure that the request body is a JSON string."
                },
                default=str,
            ),
        }

    host = parsed_event["headers"]["Host"]
    username = ".".join(host.split(".")[:-2])
    model_name = parsed_event["path"].lstrip("/")
    payload = parsed_event["body"].get("payload") or ""
    print("username: ", username)
    print("model_name: ", model_name)
    print("payload: ", payload)

    # TODO: Grab model based on host from dynamodb
    model = get_model_record(username=username, model=model_name, sk="main")
    print("model: ", json.dumps(model, default=str))

    # If model is the initial PING, return "ok"
    if model["type"] == _PING:
        return {"isBase64Encoded": False, "statusCode": 200, "body": "ok"}

    try:
        lambda_response = lambda_.invoke(
            FunctionName=EXECUTION_LAMBDA_ARN,
            InvocationType="RequestResponse",
            LogType="Tail",
            Payload=json.dumps(
                {
                    "payload": payload,
                    "model": model,
                },
                default=str,
            ).encode(),
        )
    except lambda_.exceptions.TooManyRequestsException as err:
        print(err)
        status_code, result = 429, "Too Many Requests"
    except Exception as err:
        print(err)
        status_code, result = 400, "Too Many Requests"
    else:
        status_code = 200
        result = lambda_response["Payload"].read().decode()

    response = {"result": result}

    return {
        "isBase64Encoded": False,
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",  # Required for CORS support to work
            "Access-Control-Allow-Credentials": True,  # Required for cookies, authorization headers with HTTPS
            "Access-Control-Allow-Methods": "POST",  # Allow only GET request
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(response, default=str),
    }
