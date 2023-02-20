from boto3.dynamodb.types import TypeDeserializer, TypeSerializer


def from_(dynamo_obj: dict) -> dict:
    deserializer = TypeDeserializer()
    return {k: deserializer.deserialize(v) for k, v in dynamo_obj.items()}


def to_(python_obj: dict) -> dict:
    serializer = TypeSerializer()
    return {k: serializer.serialize(v) for k, v in python_obj.items()}
