import json
from flows import delete_user_api_resources as delete

_empty = {
    "domain_name": None,
    "rest_api_id": None,
    "hosted_zone_id": None,
    "cert_arn": None,
    "dns_validation_record": None,
    "custom_domain_a_record": None,
}


def delete_resources(username: str):
    record = delete.get_record(username)
    resources = {**_empty, **record.get("resources", {})}
    print("resources: ", json.dumps(resources, default=str))
    delete.delete_resources(username, **resources)


def handler(event: dict, context):
    print("Event: ", json.dumps(event))
    if "Records" not in event:
        delete_resources(event["username"])
        return

    for k, record in enumerate(event.get("Records", [])):
        body = json.loads(record["body"])
        print(f"{k}: {record['body']}")

        delete_resources(body["username"])
