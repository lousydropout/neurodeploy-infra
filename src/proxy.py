import os
import json
import boto3

LAMBDA_ARN = os.environ["lambda"]
lambda_ = boto3.client("lambda")


def parse_event(event: dict) -> dict:
    headers = event["headers"]
    request_context = event["requestContext"]

    parsed_event = {
        "http_method": event["httpMethod"],
        "path": event["path"],
        "headers": headers,
        "body": event["body"],
        "query_params": event["queryStringParameters"],
        "identity": request_context["identity"],
        "request_epoch_time": request_context["requestTimeEpoch"],
    }

    return parsed_event


def handler(event: dict, context) -> dict:
    print("Event: ", json.dumps(event))
    parsed_event = parse_event(event)
    origin = parsed_event["headers"]["origin"]
    payload = parsed_event["body"]["payload"]

    try:
        lambda_response = lambda_.invoke(
            FunctionName="string",
            InvocationType="RequestResponse",
            LogType="Tail",
            Payload=json.dumps({"payload": payload, "model": ""}, default=str).encode(),
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
            "Access-Control-Allow-Origin": origin,  # Required for CORS support to work
            "Access-Control-Allow-Credentials": True,  # Required for cookies, authorization headers with HTTPS
            "Access-Control-Allow-Methods": "POST",  # Allow only GET request
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(response, default=str),
    }
