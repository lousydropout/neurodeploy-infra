import os
import json
import boto3

lambda_arn = os.environ["lambda"]

lambda_ = boto3.client("lambda")


def handler(event: dict, context) -> dict:
    print("Event: ", json.dumps(event))

    origin = event["headers"]["origin"]

    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": origin,  # Required for CORS support to work
            "Access-Control-Allow-Credentials": True,  # Required for cookies, authorization headers with HTTPS
            "Access-Control-Allow-Methods": "POST",  # Allow only GET request
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": "...",
    }
