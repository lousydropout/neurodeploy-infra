#!/usr/bin/env python3
import os
import aws_cdk as cdk
from nd_main.nd_main_stack import NdMainStack
from base.base_stack import BaseStack


DOMAIN_NAME = "playingwithml.com"
_REGION = "us-west-2"
_REGIONS = ["us-west-2", "us-east-1"]

ENV = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=_REGION,  # os.getenv("CDK_DEFAULT_REGION"),
)

app = cdk.App()

NdMainStack(
    app,
    "NdMainStack",
    prefix="neurodeploy",
    domain_name=DOMAIN_NAME,
    region_name=_REGION,
    env=ENV,
)
BaseStack(app, "BaseStack", prefix="neurodeploy", regions=_REGIONS, env=ENV)

app.synth()
