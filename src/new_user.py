import os
import json
from uuid import uuid4 as uuid
from flows.new_user_api import create_api_for_sub_domain

import boto3

_QUEUE = os.environ["queue"]
sqs = boto3.client("sqs")


def grab_fields(message: dict) -> tuple[bool, dict]:
    if message.get("domain_name") and message.get("username"):
        return True, {
            "domain_name": message["domain_name"],
            "username": message["username"],
        }
    return False, {}


def handler(event: dict, context):
    print("Event: ", json.dumps(event))
    if "Records" not in event:
        valid, record = grab_fields(event["Records"])
        if not valid:
            raise Exception(
                "Missing one or more of the following fields from Event body: username, domain_name"
            )

        print("Sending payload to queue. . .")
        _ = sqs.send_message(
            QueueUrl=_QUEUE,
            MessageGroupId=record["username"],
            MessageDeduplicationId=str(uuid()),
            MessageBody=json.dumps(record),
        )
        print("Sent")
        return

    for record in event["Records"]:
        body = json.loads(record["body"])
        valid, record = grab_fields(body)
        if not valid:
            raise Exception(
                "Missing one or more of the following fields from SQS message: username, domain_name"
            )

        api = create_api_for_sub_domain(**record)
        print("Created api: ", json.dumps(api, default=str))
