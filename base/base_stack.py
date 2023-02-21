from aws_cdk import aws_dynamodb as dynamodb, aws_s3 as s3, RemovalPolicy, Stack
from constructs import Construct


class BaseStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        prefix: str,
        regions: list[str],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.prefix = prefix
        self.regions = regions

        # S3 buckets
        models_s3_bucket = s3.Bucket(
            self,
            f"{prefix}_models",
            # bucket_name=f"{prefix}-models",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        logs_s3_bucket = s3.Bucket(
            self,
            f"{prefix}_logs",
            # bucket_name=f"{prefix}-logs",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # # DynamoDB tables
        users = self.create_table("users_table", name="Users")
        tokens = self.create_table("tokens_table", name="Tokens")
        models = self.create_table("models_table", name="Models")
        apis = self.create_table("apis_table", name="Apis")
        usages = self.create_table("usages_table", name="Usages")

    def create_table(
        self, id: str, name: str, enable_ttl: bool = True, ttl_atribute: str = "ttl"
    ):
        cfn_global_table = dynamodb.CfnGlobalTable(
            self,
            id,
            attribute_definitions=[
                dynamodb.CfnGlobalTable.AttributeDefinitionProperty(
                    attribute_name="pk", attribute_type="S"
                ),
                dynamodb.CfnGlobalTable.AttributeDefinitionProperty(
                    attribute_name="sk", attribute_type="S"
                ),
            ],
            key_schema=[
                dynamodb.CfnGlobalTable.KeySchemaProperty(
                    attribute_name="pk", key_type="HASH"
                ),
                dynamodb.CfnGlobalTable.KeySchemaProperty(
                    attribute_name="sk", key_type="RANGE"
                ),
            ],
            replicas=[
                dynamodb.CfnGlobalTable.ReplicaSpecificationProperty(
                    region=region,
                    point_in_time_recovery_specification=dynamodb.CfnGlobalTable.PointInTimeRecoverySpecificationProperty(
                        point_in_time_recovery_enabled=True
                    ),
                    table_class="STANDARD",
                )
                for region in self.regions
            ],
            billing_mode="PAY_PER_REQUEST",
            sse_specification=dynamodb.CfnGlobalTable.SSESpecificationProperty(
                sse_enabled=True,
                sse_type="KMS",
            ),
            stream_specification=dynamodb.CfnGlobalTable.StreamSpecificationProperty(
                stream_view_type="NEW_AND_OLD_IMAGES"
            ),
            table_name=f"{self.prefix}_{name}",
            time_to_live_specification=dynamodb.CfnGlobalTable.TimeToLiveSpecificationProperty(
                enabled=enable_ttl,
                attribute_name=ttl_atribute,
            ),
        )

        return cfn_global_table
