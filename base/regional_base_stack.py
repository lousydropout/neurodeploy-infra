from aws_cdk import RemovalPolicy, Stack, aws_ec2 as ec2, aws_s3 as s3
from constructs import Construct


class RegionalBaseStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        prefix: str,
        region: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 buckets
        self.models_bucket = s3.Bucket(
            self,
            f"{prefix}_models",
            bucket_name=f"{prefix}-models-{region}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        self.staging_bucket = s3.Bucket(
            self,
            f"{prefix}_staging",
            bucket_name=f"{prefix}-staging-{region}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        self.logs_bucket = s3.Bucket(
            self,
            f"{prefix}_logs",
            bucket_name=f"{prefix}-logs-{region}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # VPC
        self.vpc = ec2.Vpc(
            self,
            "VPC",
            vpc_name="neurodeploy-vpc",
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                ),
                ec2.SubnetConfiguration(
                    name="private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                ),
            ],
            gateway_endpoints={
                "s3": ec2.GatewayVpcEndpointOptions(
                    service=ec2.GatewayVpcEndpointAwsService.S3
                ),
                "dynamodb": ec2.GatewayVpcEndpointOptions(
                    service=ec2.GatewayVpcEndpointAwsService.DYNAMODB
                ),
            },
        )
