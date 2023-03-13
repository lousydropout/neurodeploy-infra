from typing import NamedTuple, Tuple, List, Dict
import aws_cdk as cdk
from aws_cdk import (
    Duration,
    Stack,
    aws_apigateway as apigw,
    aws_certificatemanager as acm,
    aws_dynamodb as dynamodb,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_lambda_event_sources as event_sources,
    aws_route53 as route53,
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
_IAM_FULL_PERMISSION_POLICY = "IAMFullAccess"

_INVOKE_FUNCTION = "lambda:InvokeFunction"

_JWT_SECRET_NAME = "jwt_secret"


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
        self.jwt_secret = sm.Secret.from_secret_name_v2(
            self,
            "jwt_secret",
            secret_name=_JWT_SECRET_NAME,
        )

    def import_lambda_layers(self):
        jwt_layer_arn = {
            "us-west-1": "arn:aws:lambda:us-west-1:410585721938:layer:pyjwt:1",
            "us-east-2": "arn:aws:lambda:us-east-2:410585721938:layer:pyjwt:1",
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
        tables: List[Tuple[dynamodb.Table, Permission]] = None,
        buckets: List[Tuple[s3.Bucket, Permission]] = None,
        layers: List[lambda_.LayerVersion] = None,
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
        proxy: bool = False,
        filename_overwrite: str = None,
        tables: List[Tuple[dynamodb.Table, Permission]] = None,
        buckets: List[Tuple[s3.Bucket, Permission]] = None,
        secrets: List[Tuple[str, sm.Secret]] = None,
        layers: List[lambda_.LayerVersion] = None,
        create_queue: bool = False,
    ) -> LambdaQueueTuple:
        # create resource under self.api.root if it doesn't already exist
        _resource: apigw.Resource = None
        if (resource_name, proxy) in self.apigw_resources:
            _resource = self.apigw_resources[(resource_name, proxy)]
        # didn't exist
        if not _resource:
            if not proxy:
                _resource = api.root.add_resource(resource_name)
            else:
                if (resource_name, False) in self.apigw_resources:
                    _resource = self.apigw_resources[(resource_name, False)]
                else:
                    _resource = api.root.add_resource(resource_name)
                    self.apigw_resources[(resource_name, False)] = _resource
                _resource = _resource.add_proxy(any_method=False)
            self.apigw_resources[(resource_name, proxy)] = _resource

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
            _id if not filename_overwrite else filename_overwrite,
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
        self, proxy_lambda: lambda_.Function
    ) -> Tuple[apigw.RestApi, Dict[str, LambdaQueueTuple]]:
        self.apigw_resources: Dict[str, Dict] = {}

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
            "sign-up",
            filename_overwrite="signup_POST",
            tables=[(self.users, _READ_WRITE), (self.tokens, _READ_WRITE)],
            create_queue=True,
        )
        POST_signup.lambda_function.add_environment("domain_name", self.domain_name)
        POST_signup.lambda_function.add_environment(
            "hosted_zone_id", self.hosted_zone.hosted_zone_id
        )
        POST_signup.lambda_function.add_environment(
            "proxy_lambda", proxy_lambda.function_name
        )
        proxy_lambda.grant_invoke(POST_signup.lambda_function)
        POST_signup.lambda_function.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(_ACM_FULL_PERMISSION_POLICY)
        )
        POST_signin = self.add(
            api,
            "POST",
            "sign-in",
            filename_overwrite="signin_POST",
            tables=[(self.users, _READ), (self.tokens, _READ_WRITE)],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )
        GET_access_tokens = self.add(
            api,
            "GET",
            "access_tokens",
            tables=[(self.users, _READ), (self.tokens, _READ_WRITE)],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )

        POST_ml_models = self.add(
            api,
            "POST",
            "ml_models",
            proxy=True,
            tables=[
                (self.users, _READ),
                (self.tokens, _READ),
                (self.apis, _READ_WRITE),
            ],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )
        POST_ml_models.lambda_function.add_environment(
            "account_number", self.account_number
        )
        POST_ml_models.lambda_function.add_environment(
            "proxy_lambda", proxy_lambda.function_name
        )
        proxy_lambda.grant_invoke(POST_ml_models.lambda_function)
        self.models_bucket.grant_read_write(POST_ml_models.lambda_function)
        for policy in [_IAM_FULL_PERMISSION_POLICY, _APIGW_FULL_PERMISSION_POLICY]:
            POST_ml_models.lambda_function.role.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name(policy)
            )

        DELETE_ml_models = self.add(
            api,
            "DELETE",
            "ml_models",
            proxy=True,
            tables=[
                (self.users, _READ),
                (self.tokens, _READ),
                (self.apis, _READ_WRITE),
            ],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )
        self.models_bucket.grant_read_write(DELETE_ml_models.lambda_function)
        for policy in [_IAM_FULL_PERMISSION_POLICY, _APIGW_FULL_PERMISSION_POLICY]:
            DELETE_ml_models.lambda_function.role.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name(policy)
            )

        PUT_ml_models = self.add(
            api,
            "PUT",
            "ml_models",
            proxy=True,
            tables=[
                (self.users, _READ),
                (self.tokens, _READ),
                (self.apis, _READ),
            ],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )
        PUT_ml_models.lambda_function.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                _APIGW_FULL_PERMISSION_POLICY
            )
        )
        self.models_bucket.grant_read_write(PUT_ml_models.lambda_function)

        GET_ml_models = self.add(
            api,
            "GET",
            "ml_models",
            proxy=True,
            tables=[
                (self.users, _READ),
                (self.tokens, _READ),
                (self.apis, _READ),
                (self.usages, _READ_WRITE),
            ],
            buckets=[(self.models_bucket, _READ)],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )

        GET_list_of_ml_models = self.add(
            api,
            "GET",
            "ml_models",
            filename_overwrite="ml_models_list_GET",
            tables=[
                (self.users, _READ),
                (self.tokens, _READ),
                (self.apis, _READ),
                (self.usages, _READ),
            ],
            buckets=[(self.models_bucket, _READ)],
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
                "DELETE_ml_models": DELETE_ml_models,
                "GET_ml_models": GET_ml_models,
                "GET_list_of_ml_models": GET_list_of_ml_models,
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
            environment={
                "hosted_zone_id": self.hosted_zone.hosted_zone_id,
                "region_name": self.region_name,
                "queue": self.POST_signup.queue.queue_url,
            },
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
        delete_queue = sqs.Queue(
            self,
            "delete_queue",
            visibility_timeout=Duration.minutes(15),
            retention_period=Duration.hours(12),
            fifo=True,
            content_based_deduplication=False,
            deduplication_scope=sqs.DeduplicationScope.MESSAGE_GROUP,
        )
        delete_user_lambda = lambda_.Function(
            self,
            "delete_user_lambda",
            function_name=f"{self.prefix}_delete_user",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("src"),
            handler="delete_user.handler",
            timeout=Duration.seconds(300),
            environment={
                "hosted_zone_id": self.hosted_zone.hosted_zone_id,
                "region_name": self.region_name,
                "queue": delete_queue.queue_url,
            },
            layers=[],
            reserved_concurrent_executions=2,
        )
        delete_queue.grant_send_messages(delete_user_lambda)
        delete_queue.grant_consume_messages(delete_user_lambda)
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

    def create_proxy_lambda(self) -> Tuple[lambda_.Alias, LambdaQueueTuple]:
        execution_lambda = lambda_.DockerImageFunction(
            self,
            "execution_lambda",
            function_name=f"{self.prefix}_execution",
            code=lambda_.DockerImageCode.from_ecr(
                repository=ecr.Repository.from_repository_name(
                    self, "lambda_runtime_ecr", "lambda_runtime"
                ),
                tag_or_digest=self.lambda_image_digest,
            ),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=self.subnets.subnets),
            timeout=Duration.seconds(28),
            environment={
                "region_name": self.region_name,
                "bucket": self.models_bucket.bucket_name,
                "base_image": self.lambda_image_digest,
                "domain_name": self.domain_name,
            },
            memory_size=3008,
            security_groups=[self.sg],
        )
        execution_version = execution_lambda.current_version
        execution_alias = lambda_.Alias(
            self,
            "execution_alias",
            alias_name="prod",
            version=execution_version,
            provisioned_concurrent_executions=1,
        )
        self.models_bucket.grant_read_write(execution_alias)

        proxy_lambda = lambda_.Function(
            self,
            "proxy_lambda",
            function_name=f"{self.prefix}_proxy",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("src"),
            handler="proxy.handler",
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=self.subnets.subnets),
            timeout=Duration.seconds(30),
            environment={
                "region_name": self.region_name,
                "lambda": execution_alias.function_arn,
            },
            security_groups=[self.sg],
        )
        execution_alias.grant_invoke(proxy_lambda)
        self.models.grant_read_data(proxy_lambda)

        logs_queue = sqs.Queue(
            self,
            "logs_queue",
            visibility_timeout=Duration.minutes(15),
            retention_period=Duration.hours(12),
            fifo=True,
            content_based_deduplication=False,
            deduplication_scope=sqs.DeduplicationScope.MESSAGE_GROUP,
        )

        # # Allow proxy lambda to invoke ANY lambda
        proxy_lambda.add_to_role_policy(
            iam.PolicyStatement(actions=[_INVOKE_FUNCTION], resources=["*"])
        )

        # Resource policy allowing API Gateway permission
        # Note: this allows any API Gateways from this account to invoke this proxy lambda
        _ = lambda_.CfnPermission(
            self,
            "apigw_invoke_lambda_permission",
            action=_INVOKE_FUNCTION,
            function_name=proxy_lambda.function_arn,
            principal="apigateway.amazonaws.com",
            source_account=self.account_number,
        )

        # S3 permission
        self.models_bucket.grant_read(proxy_lambda)
        self.logs_bucket.grant_read_write(proxy_lambda)

        # DynamoDB permission
        self.apis.grant_read_data(proxy_lambda)
        proxy_lambda.add_environment(self.apis.table_name, self.apis.table_arn)

        self.usages.grant_full_access(proxy_lambda)
        proxy_lambda.add_environment(self.usages.table_name, self.usages.table_arn)

        # SQS queue permission
        logs_queue.grant_send_messages(proxy_lambda)

        return execution_alias, LambdaQueueTuple(proxy_lambda, logs_queue)

    def create_security_group(self) -> ec2.SecurityGroup:
        sg = ec2.SecurityGroup(
            self,
            "proxy_lambda_sg",
            vpc=self.vpc,
            security_group_name="proxy_lambda_sg",
            allow_all_outbound=True,
        )
        sg.connections.allow_internally(
            port_range=ec2.Port.all_traffic(),
            description="Allow all traffic from the same security group",
        )
        return sg

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        prefix: str,
        domain_name: str,
        region_name: str,
        account_number: str,
        buckets: Dict[str, s3.Bucket],
        vpc: ec2.Vpc,
        lambda_image: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.account_number = account_number
        self.prefix = prefix
        self.region_name = region_name
        self.domain_name = domain_name

        self.models_bucket = buckets["models_bucket"]
        self.logs_bucket = buckets["models_bucket"]

        self.vpc = vpc
        self.subnets = self.vpc.select_subnets(
            subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
        )

        self.lambda_image_digest = lambda_image

        # Imports
        self.import_secrets()
        self.import_lambda_layers()
        self.import_databases()

        # DNS
        self.hosted_zone = self.import_hosted_zone()
        self.main_cert = self.create_cert_for_domain()

        # security group for proxy lambda & execution lambda
        self.sg = self.create_security_group()

        # proxy lambda + logs queue
        self.execution_alias, self.proxy = self.create_proxy_lambda()

        # API Gateway and lambda-integrated routes
        self.api, rest = self.create_api_gateway_and_lambdas(self.proxy.lambda_function)
        self.POST_signup = rest["POST_signup"]
        self.POST_signin = rest["POST_signin"]
        self.GET_access_token = rest["GET_access_tokens"]
        self.POST_ml_models = rest["POST_ml_models"]
        self.PUT_ml_models = rest["PUT_ml_models"]
        self.GET_ml_models = rest["GET_ml_models"]
        self.GET_list_of_ml_models = rest["GET_list_of_ml_models"]
        self.DELETE_ml_models = rest["DELETE_ml_models"]

        # Add proxy lambda to apigw
        self.proxy_resource = self.api.root.add_proxy(
            any_method=False,
            default_integration=apigw.Integration(
                type=apigw.IntegrationType.AWS_PROXY,
                integration_http_method="POST",
                uri=(
                    f"arn:aws:apigateway:{self.region_name}:"
                    "lambda:path/2015-03-31/functions/arn:"
                    f"aws:lambda:{self.region_name}:{self.account_number}:function:"
                    f"{self.proxy.lambda_function.function_name}/invocations"
                ),
            ),
        )
        self.proxy_resource.add_method(
            http_method="POST",
            integration=apigw.LambdaIntegration(self.proxy.lambda_function),
        )

        # Additional lambdas
        self.new_user_lambda = self.create_new_user_lambda()
        self.delete_user_lambda = self.create_delete_user_lambda()
