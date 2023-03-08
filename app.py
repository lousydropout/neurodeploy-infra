#!/usr/bin/env python3
import os
import aws_cdk as cdk
from main.main_stack import MainStack
from base.base_stack import BaseStack
from base.regional_base_stack import RegionalBaseStack


DOMAIN_NAME = "playingwithml.com"
_PREFIX = "neurodeploy"
_ACCOUNT = os.getenv("CDK_DEFAULT_ACCOUNT")
_REGION_1 = "us-west-1"
_REGION_2 = "us-east-2"
_REGIONS = [_REGION_1, _REGION_2]

_BASE_IMAGE = {
    _REGION_1: "sha256:530aa8e894125aa5dfa8c0c8d3d21dac85c1191eb23542c76acc8a7b09b15ce7",
    _REGION_2: "sha256:530aa8e894125aa5dfa8c0c8d3d21dac85c1191eb23542c76acc8a7b09b15ce7",
}

app = cdk.App()

base_stack = BaseStack(
    app,
    "BaseStack",
    prefix=_PREFIX,
    regions=_REGIONS,
    env=cdk.Environment(account=_ACCOUNT, region=_REGION_1),
)

base = {
    f"RegionalBase-{region}": RegionalBaseStack(
        app,
        f"RegionalBase-{region}",
        prefix=_PREFIX,
        region=region,
        env=cdk.Environment(account=_ACCOUNT, region=region),
    )
    for region in _REGIONS
}

for region in _REGIONS:
    MainStack(
        app,
        f"MainStack-{region}",
        prefix=_PREFIX,
        domain_name=DOMAIN_NAME,
        account_number=_ACCOUNT,
        region_name=region,
        buckets={"models_bucket": base[f"RegionalBase-{region}"].models_bucket},
        vpc=base[f"RegionalBase-{region}"].vpc,
        lambda_image=_BASE_IMAGE[region],
        env=cdk.Environment(account=_ACCOUNT, region=region),
    )

app.synth()
