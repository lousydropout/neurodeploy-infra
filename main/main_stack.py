from typing import Dict, NamedTuple, Tuple
import aws_cdk as cdk
from aws_cdk import (
    Duration,
    Stack,
    aws_apigateway as apigw,
    aws_certificatemanager as acm,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_lambda_event_sources as event_sources,
    aws_route53 as route53,
    aws_route53_targets as targets,
    aws_s3 as s3,
    aws_secretsmanager as sm,
    aws_sqs as sqs,
)
from constructs import Construct
from enum import Enum


class LambdaQueueTuple(NamedTuple):
    lambda_function: lambda_.Function
    queue: sqs.Queue


class Permission(Enum):
    READ = "READ"
    WRITE = "WRITE"
    READ_WRITE = "READ_WRITE"


_READ = Permission.READ
_WRITE = Permission.WRITE
_READ_WRITE = Permission.READ_WRITE

_ACM_FULL_PERMISSION_POLICY = "AWSCertificateManagerFullAccess"
_SQS_FULL_PERMISSION_POLICY = "AmazonSQSFullAccess"
_ROUTE_53_FULL_PERMISSION_POLICY = "AmazonRoute53FullAccess"
_APIGW_FULL_PERMISSION_POLICY = "AmazonAPIGatewayAdministrator"
_LAMBDA_PERMISSION_POLICY = "AWSLambdaRole"


class MainStack(Stack):
    def import_dynamodb_table(self, name: str) -> dynamodb.ITable:
        return dynamodb.Table.from_table_name(self, name, f"{self.prefix}_{name}")

    def import_databases(self):
        self.users: dynamodb.Table = self.import_dynamodb_table("Users")
        self.tokens: dynamodb.Table = self.import_dynamodb_table("Tokens")
        self.models: dynamodb.Table = self.import_dynamodb_table("Models")
        self.apis: dynamodb.Table = self.import_dynamodb_table("Apis")
        self.usages: dynamodb.Table = self.import_dynamodb_table("Usages")

    def import_secrets(self):
        _JWT_SECRET_NAME = "neurodeploy/mvp/jwt-secrets"
        self.jwt_secret = sm.Secret.from_secret_name_v2(
            self,
            "jwt_secret",
            secret_name=_JWT_SECRET_NAME,
        )

    def import_lambda_layers(self):
        jwt_layer_arn = {
            "us-west-2": "arn:aws:lambda:us-west-2:410585721938:layer:pyjwt:1",
            "us-west-1": "arn:aws:lambda:us-west-1:410585721938:layer:pyjwt:1",
            "us-east-2": "	arn:aws:lambda:us-east-2:410585721938:layer:pyjwt:1",
        }

        self.py_jwt_layer = lambda_.LayerVersion.from_layer_version_arn(
            self,
            "py_jwt_layer",
            layer_version_arn=jwt_layer_arn[self.region],
        )

    def import_hosted_zone(self) -> route53.IHostedZone:
        zone = route53.HostedZone.from_lookup(
            self,
            "HostedZone",
            domain_name=self.domain_name,
        )
        return zone

    def create_lambda(
        self,
        id: str,
        tables: list[Tuple[dynamodb.Table, Permission]] = None,
        buckets: list[Tuple[s3.Bucket, Permission]] = None,
        layers: list[lambda_.LayerVersion] = None,
        queue: sqs.Queue = None,
    ) -> lambda_.Function:
        # environment variables for the lambda function
        env = {table.table_name: table.table_arn for (table, _) in tables}
        env["region_name"] = self.region_name
        if queue:
            env["queue"] = queue.queue_url

        # create lambda function
        _lambda = lambda_.Function(
            self,
            id,
            function_name=f"{self.prefix}_{id}",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("src"),
            handler=f"{id}.handler",
            environment=env,
            timeout=Duration.seconds(29),
            layers=layers or [],
        )

        # grant lambda function access to DynamoDB tables
        for table, permission in tables or []:
            if permission == _READ:
                table.grant_read_data(_lambda)
            elif permission == _WRITE:
                table.grant_write_data(_lambda)
            else:
                table.grant_full_access(_lambda)

        # grant lambda function access to S3 buckets
        for bucket, permission in buckets or []:
            if permission == _READ:
                bucket.grant_read(_lambda)
            elif permission == _WRITE:
                bucket.grant_write(_lambda)
            else:
                bucket.grant_read_write(_lambda)

        return _lambda

    def add(
        self,
        api: apigw.RestApi,
        http_method: str,
        resource_name: str,
        tables: list[Tuple[dynamodb.Table, Permission]] = None,
        buckets: list[Tuple[s3.Bucket, Permission]] = None,
        secrets: list[Tuple[str, sm.Secret]] = None,
        layers: list[lambda_.LayerVersion] = None,
        create_queue: bool = False,
    ) -> LambdaQueueTuple:
        # create resource under self.api.root if it doesn't already exist
        _resource: apigw.Resource = None
        if resource_name in self.apigw_resources:
            _resource = self.apigw_resources[resource_name]
        if not _resource:
            _resource = api.root.add_resource(resource_name)
            self.apigw_resources[resource_name] = _resource

        # create lambda
        _id = f"{resource_name}_{http_method}"
        _queue = (
            sqs.Queue(
                self,
                resource_name,
                visibility_timeout=Duration.minutes(15),
                retention_period=Duration.hours(12),
                fifo=True,
                content_based_deduplication=False,
                deduplication_scope=sqs.DeduplicationScope.MESSAGE_GROUP,
            )
            if create_queue
            else None
        )
        _lambda = self.create_lambda(
            _id,
            tables=tables,
            buckets=buckets,
            layers=layers,
            queue=_queue,
        )
        if _queue:
            _queue.grant_send_messages(_lambda)

        # add method to resource as proxy to _lambda
        _resource.add_method(http_method, apigw.LambdaIntegration(_lambda))

        # grant lambda permission to read secret
        for secret_name, secret in secrets or []:
            secret.grant_read(_lambda)
            _lambda.add_environment(secret_name, secret.secret_name)

        return LambdaQueueTuple(_lambda, _queue)

    def create_cert_for_domain(self) -> acm.Certificate:
        return acm.Certificate(
            self,
            "Certificate",
            domain_name=f"*.{self.domain_name}",
            validation=acm.CertificateValidation.from_dns(self.hosted_zone),
        )

    def create_api_gateway_and_lambdas(
        self,
    ) -> Tuple[apigw.RestApi, Dict[str, LambdaQueueTuple]]:
        self.apigw_resources: Dict[str, apigw.Resource] = {}

        api = apigw.RestApi(
            self,
            id=f"{self.prefix}_api",
            endpoint_types=[apigw.EndpointType.REGIONAL],
        )
        domain_name = apigw.DomainName(
            self,
            f"{self.domain_name}_domain_name",
            mapping=api,
            certificate=self.main_cert,
            domain_name=f"api.{self.domain_name}",
        )

        POST_signup = self.add(
            api,
            "POST",
            "signup",
            tables=[(self.users, _READ_WRITE), (self.tokens, _READ_WRITE)],
            create_queue=True,
        )
        POST_signup.lambda_function.add_environment("domain_name", self.domain_name)
        POST_signup.lambda_function.add_environment(
            "hosted_zone_id", self.hosted_zone.hosted_zone_id
        )
        POST_signup.lambda_function.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(_ACM_FULL_PERMISSION_POLICY)
        )
        POST_signin = self.add(
            api,
            "POST",
            "signin",
            tables=[(self.users, _READ), (self.tokens, _READ_WRITE)],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )
        GET_access_tokens = self.add(
            api,
            "GET",
            "access_tokens",
            tables=[(self.users, _READ_WRITE), (self.tokens, _READ_WRITE)],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )

        POST_ml_models = self.add(
            api,
            "POST",
            "ml_models",
            tables=[
                (self.users, _READ_WRITE),
                (self.tokens, _READ_WRITE),
                (self.apis, _READ_WRITE),
                (self.models, _READ_WRITE),
            ],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )
        PUT_ml_models = self.add(
            api,
            "PUT",
            "ml_models",
            tables=[
                (self.users, _READ_WRITE),
                (self.tokens, _READ_WRITE),
                (self.apis, _READ_WRITE),
                (self.models, _READ_WRITE),
            ],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )
        GET_ml_models = self.add(
            api,
            "GET",
            "ml_models",
            tables=[
                (self.users, _READ_WRITE),
                (self.tokens, _READ_WRITE),
                (self.apis, _READ_WRITE),
                (self.models, _READ_WRITE),
                (self.usages, _READ_WRITE),
            ],
            buckets=[(self.models_bucket, _READ_WRITE)],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )

        # DNS records
        target = route53.CfnRecordSet.AliasTargetProperty(
            dns_name=domain_name.domain_name_alias_domain_name,
            hosted_zone_id=domain_name.domain_name_alias_hosted_zone_id,
            evaluate_target_health=False,
        )

        self.api_record = route53.CfnRecordSet(
            self,
            "ApiARecord",
            name=f"api.{self.domain_name}",
            type="A",
            alias_target=target,
            hosted_zone_id=self.hosted_zone.hosted_zone_id,
            weight=100,
            set_identifier=cdk.Aws.STACK_NAME,
        )

        return (
            api,
            {
                "POST_signup": POST_signup,
                "POST_signin": POST_signin,
                "GET_access_tokens": GET_access_tokens,
                "POST_ml_models": POST_ml_models,
                "PUT_ml_models": PUT_ml_models,
                "GET_ml_models": GET_ml_models,
            },
        )

    def create_new_user_lambda(self) -> lambda_.Function:
        new_user_lambda = lambda_.Function(
            self,
            "new_user_lambda",
            function_name=f"{self.prefix}_new_user",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("src"),
            handler="new_user.handler",
            timeout=Duration.seconds(300),
            environment={"hosted_zone_id": self.hosted_zone.hosted_zone_id},
            layers=[],
            reserved_concurrent_executions=2,
        )
        self.POST_signup.queue.grant_consume_messages(new_user_lambda)
        self.POST_signup.queue.grant_send_messages(new_user_lambda)
        new_user_lambda.add_event_source(
            event_sources.SqsEventSource(self.POST_signup.queue, batch_size=1)
        )
        permissions = [
            _ACM_FULL_PERMISSION_POLICY,
            _SQS_FULL_PERMISSION_POLICY,
            _ROUTE_53_FULL_PERMISSION_POLICY,
            _APIGW_FULL_PERMISSION_POLICY,
        ]
        for permission in permissions:
            new_user_lambda.role.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name(permission)
            )
        self.apis.grant_read_write_data(new_user_lambda)
        new_user_lambda.add_environment(self.apis.table_name, self.apis.table_arn)

        return new_user_lambda

    def create_delete_user_lambda(self) -> lambda_.Function:
        delete_user_lambda = lambda_.Function(
            self,
            "delete_user_lambda",
            function_name=f"{self.prefix}_delete_user",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("src"),
            handler="delete_user.handler",
            timeout=Duration.seconds(300),
            environment={"hosted_zone_id": self.hosted_zone.hosted_zone_id},
            layers=[],
            reserved_concurrent_executions=2,
        )
        permissions = [
            _ACM_FULL_PERMISSION_POLICY,
            _SQS_FULL_PERMISSION_POLICY,
            _ROUTE_53_FULL_PERMISSION_POLICY,
            _APIGW_FULL_PERMISSION_POLICY,
        ]
        for permission in permissions:
            delete_user_lambda.role.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name(permission)
            )
        self.apis.grant_read_write_data(delete_user_lambda)
        delete_user_lambda.add_environment(self.apis.table_name, self.apis.table_arn)

        return delete_user_lambda

    def create_proxy_lambda(self) -> LambdaQueueTuple:
        proxy_lambda = lambda_.Function(
            self,
            "proxy_lambda",
            function_name=f"{self.prefix}_proxy",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("src"),
            handler="proxy.handler",
            timeout=Duration.seconds(30),
        )

        logs_queue = sqs.Queue(
            self,
            "logs_queue",
            visibility_timeout=Duration.minutes(15),
            retention_period=Duration.hours(12),
            fifo=True,
            content_based_deduplication=False,
            deduplication_scope=sqs.DeduplicationScope.MESSAGE_GROUP,
        )

        # S3 permission

        # DynamoDB permission
        self.apis.grant_read_data(proxy_lambda)
        proxy_lambda.add_environment(self.apis.table_name, self.apis.table_arn)

        self.usages.grant_full_access(proxy_lambda)
        proxy_lambda.add_environment(self.usages.table_name, self.usages.table_arn)

        # SQS queue permission
        logs_queue.grant_send_messages(proxy_lambda)

        # invoke other lambdas permission
        proxy_lambda.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(_LAMBDA_PERMISSION_POLICY)
        )

        return LambdaQueueTuple(proxy_lambda, logs_queue)

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        prefix: str,
        domain_name: str,
        region_name: str,
        buckets: Dict[str, s3.Bucket],
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.prefix = prefix
        self.region_name = region_name
        self.domain_name = domain_name

        self.models_bucket = buckets["models_bucket"]
        self.logs_bucket = buckets["models_bucket"]

        # Imports
        self.import_secrets()
        self.import_lambda_layers()
        self.import_databases()

        # DNS
        self.hosted_zone = self.import_hosted_zone()
        self.main_cert = self.create_cert_for_domain()

        # API Gateway and lambda-integrated routes
        self.api, rest = self.create_api_gateway_and_lambdas()
        self.POST_signup = rest["POST_signup"]
        self.POST_signin = rest["POST_signin"]
        self.GET_access_token = rest["GET_access_tokens"]
        self.POST_ml_models = rest["POST_ml_models"]
        self.PUT_ml_models = rest["PUT_ml_models"]
        self.GET_ml_models = rest["GET_ml_models"]

        # Additional lambdas
        self.new_user_lambda = self.create_new_user_lambda()
        self.delete_user_lambda = self.create_delete_user_lambda()

        # proxy lambda + logs queue
        # self.proxy = self.create_proxy_lambda()
