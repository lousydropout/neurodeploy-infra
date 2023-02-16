import os
from typing import Tuple
import json
from hashlib import sha256

UTF_8 = "utf-8"

_USERS = os.environ["neurodeploy_Users"]
_SESSIONS = os.environ["neurodeploy_Sessions"]


def if_password_correct(password: str, salt: str, hashed: str) -> bool:
    return sha256((password + salt).encode(UTF_8)).hexdigest() == hashed


def parse(event: dict) -> Tuple[dict, dict]:
    """Return a parsed version of the API Gateway event (with password salted and hashed)."""
    # get body
    body: dict[str, str] = json.loads(event["body"])

    # other stuff
    request_context = event["requestContext"]
    identity = request_context["identity"]

    parsed_event = {
        "http_method": event["httpMethod"],
        "path": event["path"],
        "query_params": event["queryStringParameters"],
        "headers": event["headers"],
        "protocol": request_context["protocol"],
        "domain_name": request_context["domainName"],
        "request_epoch_time": request_context["requestTimeEpoch"],
        "api_id": request_context["apiId"],
        "stage": request_context["stage"],
        "ip_source": identity["sourceIp"],
        "identity": identity,
    }

    return body, parsed_event


def handler(event: dict, context):
    body, parsed_event = parse(event)
    print("Event: ", json.dumps(parsed_event))

    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": "logged in",
    }
