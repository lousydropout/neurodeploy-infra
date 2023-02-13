from aws_cdk import aws_dynamodb as dynamodb, RemovalPolicy, Stack
from constructs import Construct


class DatabaseStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, prefix: str, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        users = dynamodb.Table(
            self,
            f"{prefix}_Users",
            table_name=f"{prefix}_Users",
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            partition_key=dynamodb.Attribute(
                name="pk",
                type=dynamodb.AttributeType.STRING,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        sessions = dynamodb.Table(
            self,
            f"{prefix}_Sessions",
            table_name=f"{prefix}_Sessions",
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            partition_key=dynamodb.Attribute(
                name="pk",
                type=dynamodb.AttributeType.STRING,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        apis = dynamodb.Table(
            self,
            f"{prefix}_APIs",
            table_name=f"{prefix}_APIs",
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            partition_key=dynamodb.Attribute(
                name="pk",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="sk",
                type=dynamodb.AttributeType.STRING,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        models = dynamodb.Table(
            self,
            f"{prefix}_Models",
            table_name=f"{prefix}_Models",
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            partition_key=dynamodb.Attribute(
                name="pk",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="sk",
                type=dynamodb.AttributeType.STRING,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        usage_logs = dynamodb.Table(
            self,
            f"{prefix}_UsageLogs",
            table_name=f"{prefix}_UsageLogs",
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            partition_key=dynamodb.Attribute(
                name="pk",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="sk",
                type=dynamodb.AttributeType.STRING,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )
