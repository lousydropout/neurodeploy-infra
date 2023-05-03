#!/usr/bin/env python3
import os
import aws_cdk as cdk
from main.main_stack import MainStack
from base.base_stack import BaseStack
from base.regional_base_stack import RegionalBaseStack
import boto3

_ACCOUNT = os.getenv("CDK_DEFAULT_ACCOUNT")
if _ACCOUNT == "410585721938":
    env_ = "prod"
    DOMAIN_NAME = "neurodeploy.com"
    _PREFIX = "neurodeploy"
    _REGION_1 = "us-west-1"
    _REGION_2 = "us-east-2"
    _REGIONS = [_REGION_1, _REGION_2]
elif _ACCOUNT == "460216766486":
    env_ = "dev"
    DOMAIN_NAME = "playingwithml.com"
    _PREFIX = "playingwithml"
    _REGION_1 = "us-east-1"
    _REGION_2 = "us-west-1"
    _REGIONS = [_REGION_1, _REGION_2]
else:
    raise Exception("Invalid env var: env")


app = cdk.App()

base_stack = BaseStack(
    app,
    "BaseStack" if env_ == "dev" else "BaseStack-prod",
    prefix=_PREFIX,
    regions=_REGIONS,
    env=cdk.Environment(account=_ACCOUNT, region=_REGION_1),
    tags={
        "stack": "base",
        "domain": "playingwithml.com",
    },
)

base = {
    f"RegionalBase-{region}": RegionalBaseStack(
        app,
        f"RegionalBase-{region}" if env_ == "dev" else f"RegionalBase-{region}-prod",
        prefix=_PREFIX,
        region=region,
        env=cdk.Environment(account=_ACCOUNT, region=region),
        tags={
            "stack": "regional",
            "domain": "playingwithml.com",
            "region": region,
        },
    )
    for region in _REGIONS
}

for region in _REGIONS:
    MainStack(
        app,
        f"MainStack-{region}" if env_ == "dev" else f"MainStack-{region}-prod",
        prefix=_PREFIX,
        domain_name=DOMAIN_NAME,
        account_number=_ACCOUNT,
        region_name=region,
        other_regions=[x for x in _REGIONS if x != region],
        buckets={"models_bucket": base[f"RegionalBase-{region}"].models_bucket},
        vpc=base[f"RegionalBase-{region}"].vpc,
        env_=env_,
        env=cdk.Environment(account=_ACCOUNT, region=region),
        tags={
            "stack": "main",
            "domain": "playingwithml.com",
            "region": region,
        },
    )

app.synth()
