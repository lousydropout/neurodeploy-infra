import json


def handler(event: dict, context):
    print(f"Event: {json.dumps(event)}")

    http_method = event["httpMethod"]
    path = event["path"]

    headers = event["headers"]
    body = event["body"]
    query_params = event["queryStringParameters"]
    request_context = event["requestContext"]
    request_epoch_time = request_context["requestTimeEpoch"]
    identity = request_context["identity"]
    ip_source = identity["sourceIp"]
    user_agent = identity["userAgent"]

    return {
        "isBase64Encoded": False,
        "statusCode": 201,
        "headers": {"headerName": "headerValue"},
        "body": "...",
    }
