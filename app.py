#!/usr/bin/env python3
import os
import aws_cdk as cdk
from nd_main.nd_main_stack import NdMainStack
from database.database_stack import DatabaseStack


DOMAIN_NAME = "whinypuppy.com"
ENV = cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region="us-west-2",  # os.getenv("CDK_DEFAULT_REGION"),
    )
app = cdk.App()
NdMainStack(
    app,
    "NdMainStack",
    prefix="neurodeploy",
    domain_name=DOMAIN_NAME,
    env=ENV,
)
DatabaseStack(
    app,
    "DatabaseStack",
    prefix="neurodeploy",
    env=ENV,
)
app.synth()
