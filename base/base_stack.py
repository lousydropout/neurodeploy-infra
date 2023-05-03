from typing import List
from tagging import add_tags
from aws_cdk import (
    aws_dynamodb as dynamodb,
    aws_secretsmanager as sm,
    RemovalPolicy,
    Stack,
)
from constructs import Construct


class BaseStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        prefix: str,
        regions: List[str],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.prefix = prefix
        self.regions = regions
        self.replica_regions = [sm.ReplicaRegion(region=r) for r in regions[1:]]

        # # DynamoDB tables
        users = self.create_table("users_table", name="Users")
        creds = self.create_table("creds_table", name="Creds")
        models = self.create_table("models_table", name="Models")
        usages = self.create_table("usages_table", name="Usages")

        # Secrets
        self.jwt_secret = sm.Secret(
            self,
            f"{self.prefix}_jwt_secret",
            secret_name=f"{self.prefix}_jwt_secret",
            replica_regions=self.replica_regions,
            removal_policy=RemovalPolicy.RETAIN,
        )

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
        add_tags(cfn_global_table, {"table": name})

        return cfn_global_table
