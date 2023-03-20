import json


def handler(event: dict, context) -> dict:
    # 1. Parse event
    print("Event: ", json.dumps(event))

    response = {
        "isBase64Encoded": False,
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",  # Required for CORS support to work
            "Access-Control-Allow-Credentials": True,  # Required for cookies, authorization headers with HTTPS
            "Access-Control-Allow-Methods": "*",  # Allow only GET request
            "Access-Control-Allow-Headers": "*",
        },
        "body": json.dumps({}),
    }
    print("Response: ", json.dumps(response))
    return response
