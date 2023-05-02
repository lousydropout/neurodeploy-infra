from typing import Dict
import aws_cdk as cdk
from constructs import IConstruct


def add_tags(construct: IConstruct, tags: Dict[str, str]):
    for k, v in tags.items():
        cdk.Tags.of(construct).add(k, v)
