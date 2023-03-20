def handler(event: dict, context) -> dict:
    return {
        "isBase64Encoded": False,
        "statusCode": 204,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",  # Required for CORS support to work
            "Access-Control-Allow-Credentials": True,  # Required for cookies, authorization headers with HTTPS
            "Access-Control-Allow-Methods": "*",  # Allow only POST request
            "Access-Control-Allow-Headers": "*",
        },
    }
