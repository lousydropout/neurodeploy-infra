from helpers import validation


@validation.check_authorization
def handler(event: dict, context):
    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "headers": {"headerName": "headerValue"},
        "body": "valid token",
    }
