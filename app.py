#!/usr/bin/env python3
import os
import aws_cdk as cdk
from main.main_stack import MainStack
from base.base_stack import BaseStack


DOMAIN_NAME = "playingwithml.com"
_PREFIX = "neurodeploy"
_REGION = "us-west-1"
_REGIONS = ["us-west-1", "us-east-2"]

ENV = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=_REGION,  # os.getenv("CDK_DEFAULT_REGION"),
)

app = cdk.App()

MainStack(
    app,
    "MainStack",
    prefix=_PREFIX,
    domain_name=DOMAIN_NAME,
    region_name=_REGION,
    env=ENV,
)
BaseStack(app, "BaseStack", prefix=_PREFIX, regions=_REGIONS, env=ENV)

app.synth()
