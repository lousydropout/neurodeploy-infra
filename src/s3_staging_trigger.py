import json


def handler(event: dict, context):
    print("Event: ", json.dumps(event))
