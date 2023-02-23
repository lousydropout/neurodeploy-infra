from aws_cdk import RemovalPolicy, Stack, aws_s3 as s3, aws_secretsmanager as sm
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

        # Secrets
        self.jwt_secret = sm.Secret(self, "jwt_secret", secret_name="jwt_secret")
