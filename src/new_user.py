import json
from flows.new_user_api import create_api_for_sub_domain


def handler(event: dict, context):
    print("Event: ", json.dumps(event))
    if "Records" not in event:
        return

    for record in event["Records"]:
        body = json.loads(record["body"])

        username = body["username"]
        domain_name = body["domain_name"]
        api = create_api_for_sub_domain(domain_name=domain_name, sub=username)
        print("Created api: ", json.dumps(api, default=str))
