import os
import json
from flows import delete_user_api_resources as delete
from helpers.logging import logger

_REGION_NAME = os.environ["region_name"]
_empty = {
    "region_name": "Not provided",
    "domain_name": None,
    "rest_api_id": None,
    "hosted_zone_id": None,
    "cert_arn": None,
    "dns_validation_record": None,
    "custom_domain_a_record": None,
}


def delete_resources(username: str, region_name: str, **kwargs):
    # confirm that the api gateway resources were deployed in this region
    if region_name != _REGION_NAME:
        result = {
            "message": "This event is meant for a different region.",
            "username": username,
            "Indicated region": region_name,
            "Expected region": _REGION_NAME,
        }
        logger.debug("result: %s", json.dumps(result, default=str))
        return

    record = delete.get_record(username, region_name)
    resources = {**_empty, **record.get("resources", {})}

    logger.debug("resources: %s", json.dumps(resources, default=str))
    delete.delete_resources(username, **resources)


def handler(event: dict, context):
    logger.debug("Event: %s", json.dumps(event))
    if "Records" not in event:
        delete_resources(**event)
        return

    for k, record in enumerate(event.get("Records", [])):
        body = json.loads(record["body"])
        logger.debug(f"{k}: {record['body']}")
        delete_resources(**body)
