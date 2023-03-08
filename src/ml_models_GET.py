import json
from helpers import validation


@validation.check_authorization
def handler(event: dict, context):
    return {
        "isBase64Encoded": False,
        "statusCode": 201,
        "headers": {"headerName": "headerValue"},
        "body": "...",
    }
