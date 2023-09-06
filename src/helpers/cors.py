import json

AUTH_HEADERS = "Content-Type, Authorization, access_key, secret_key"


def get_response(
    body: dict | None = None,
    status_code: int = 200,
    additional_headers: str = "",
    methods: str = "*",
    origin: str = "*",
) -> dict:
    headers = AUTH_HEADERS
    if additional_headers:
        headers = ", ".join([AUTH_HEADERS, additional_headers])

    result = {"body": json.dumps(body, default=str)} if body else {"body": ""}
    result = {
        **result,
        "isBase64Encoded": False,
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": origin,  # Required for CORS support to work
            "Access-Control-Allow-Credentials": True,  # Required for cookies, authorization headers with HTTPS
            "Access-Control-Allow-Methods": methods,  # Allow only GET request
            "Access-Control-Allow-Headers": headers,
        },
    }

    return result
