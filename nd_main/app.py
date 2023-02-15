#!/usr/bin/env python3
import os
import aws_cdk as cdk
from nd_main.nd_main_stack import NdMainStack


DOMAIN_NAME = "whinypuppy.com"

app = cdk.App()
NdMainStack(
    app,
    "NdMainStack",
    prefix="neurodeploy",
    domain_name=DOMAIN_NAME,
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region="us-west-2",  # os.getenv("CDK_DEFAULT_REGION"),
    ),
)

app.synth()
