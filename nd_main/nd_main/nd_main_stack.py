from typing import Dict, NamedTuple
from aws_cdk import (
    Duration,
    Stack,
    aws_apigateway as apigw,
    aws_sqs as sqs,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
)
from constructs import Construct


class LambdaQueueTuple(NamedTuple):
    lambda_function: lambda_.Function
    queue: sqs.Queue


class NdMainStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, prefix: str, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.prefix = prefix

        # DynamoDB Table imports
        self.users: dynamodb.Table = self.import_dynamodb_table("Users")
        self.apis: dynamodb.Table = self.import_dynamodb_table("APIs")
        self.sessions: dynamodb.Table = self.import_dynamodb_table("Sessions")
        self.models: dynamodb.Table = self.import_dynamodb_table("Models")
        self.usage_logs: dynamodb.Table = self.import_dynamodb_table("UsageLogs")

        # API Gateway
        self.apigw_resources: Dict[str, apigw.Resource] = {}
        self.api = apigw.RestApi(self, f"{prefix}_api")
        signup = self.add("POST", "signup", tables=[self.users], create_queue=True)
        signin = self.add("POST", "signin", tables=[self.users, self.sessions])
        access_token = self.add(
            "GET",
            "access_token",
            tables=[
                self.users,
                self.sessions,
                self.apis,
                self.models,
                self.usage_logs,
            ],
        )

    def create_lambda(
        self,
        id: str,
        tables: list[dynamodb.Table],
        queue: sqs.Queue = None,
    ) -> lambda_.Function:
        env = {table.table_name: table.table_arn for table in tables}
        if queue:
            env["queue"] = queue.queue_url

        _lambda = lambda_.Function(
            self,
            id,
            function_name=f"{self.prefix}_{id}",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("src"),
            handler=f"{id}.handler",
            environment=env,
            timeout=Duration.seconds(29),
        )

        for table in tables:
            table.grant_full_access(_lambda)

        return _lambda

    def add(
        self,
        http_method: str,
        resource_name: str,
        tables: list[dynamodb.Table],
        create_queue: bool = False,
    ) -> LambdaQueueTuple:
        # create resource under self.api.root if it doesn't already exist
        _resource: apigw.Resource = None
        if resource_name in self.apigw_resources:
            _resource = self.apigw_resources[resource_name]
        if not _resource:
            _resource = self.api.root.add_resource(resource_name)
            self.apigw_resources[resource_name] = _resource

        # create lambda
        _id = f"{resource_name}_{http_method}"
        _queue = sqs.Queue(self, resource_name) if create_queue else None
        _lambda: lambda_.Function = self.create_lambda(_id, tables, _queue)
        if _queue:
            _queue.grant_send_messages(_lambda)

        # add method to resource as proxy to _lambda
        _resource.add_method(http_method, apigw.LambdaIntegration(_lambda))

        return LambdaQueueTuple(_lambda, _queue)

    def import_dynamodb_table(self, name: str) -> dynamodb.Table:
        return dynamodb.Table.from_table_name(self, name, f"{self.prefix}_{name}")
