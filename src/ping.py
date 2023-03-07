import json


def handler(event: dict, context) -> dict:
    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": "ok",
    }
