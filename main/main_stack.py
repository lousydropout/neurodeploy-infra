from typing import NamedTuple, Tuple, List, Dict
from tagging import add_tags
import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
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
    aws_sns as sns,
    aws_sns_subscriptions as sns_subs,
    aws_sqs as sqs,
)
from constructs import Construct
from enum import Enum
import boto3


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
_SNS_FULL_PERMISSION_POLICY = "AmazonSNSFullAccess"

_JWT_SECRET_NAME = "jwt_secret"
_USER_API = "user-api"


class RouteResource:
    def __init__(self, paths: list[str], resource: apigw.IResource):
        self.routes = {}
        for path in sorted(paths):
            nodes = ("root" + path).rstrip("/").split("/")
            self.add_child(self.routes, nodes, resource)

    def add_child(self, curr: dict, nodes: list[str], resource: apigw.IResource):
        # base case
        if not nodes:
            return

        # special rule for "root"
        node = "/" if nodes[0] == "root" else nodes[0]

        # recurse
        if node == "/" and node not in curr:
            curr[node] = {"_parent": curr, "_resource": resource}
        if node not in curr:
            # add resource
            resource = resource.add_resource(node)

            curr[node] = {"_parent": curr, "_resource": resource}
        try:
            self.add_child(curr[node], nodes[1:], curr[node]["_resource"])
        except Exception as err:
            print("err: ", err)
            print("node: ", node)
            print("self.routes: ", self.routes)
            raise Exception("Some error", err=err, node=node, routes=self.routes)

    def get(self, route: str) -> apigw.IResource:
        target = self.routes
        nodes = ("root" + route).rstrip("/").split("/")
        while nodes:
            node = "/" if nodes[0] == "root" else nodes[0]
            if nodes:
                nodes = nodes[1:]
                target = target[node]
        return target["_resource"]


class MainStack(Stack):
    def import_dynamodb_table(self, name: str) -> dynamodb.ITable:
        return dynamodb.Table.from_table_name(self, name, f"{self.prefix}_{name}")

    def import_databases(self):
        self.users: dynamodb.Table = self.import_dynamodb_table("Users")
        self.creds: dynamodb.Table = self.import_dynamodb_table("Creds")
        self.models: dynamodb.Table = self.import_dynamodb_table("Models")
        self.usages: dynamodb.Table = self.import_dynamodb_table("Usages")

    def import_secrets(self):
        self.jwt_secret = sm.Secret.from_secret_name_v2(
            self,
            "jwt_secret",
            secret_name=_JWT_SECRET_NAME,
        )

    def import_lambda_layers(self):
        jwt_layer_arn = {
            "prod": {
                "us-east-1": "arn:aws:lambda:us-east-1:460216766486:layer:pyjwt:1",
                "us-west-1": "arn:aws:lambda:us-west-1:460216766486:layer:pyjwt:1",
            },
            "dev": {
                "us-east-1": "arn:aws:lambda:us-east-1:460216766486:layer:pyjwt:1",
                "us-west-1": "arn:aws:lambda:us-west-1:460216766486:layer:pyjwt:1",
            },
        }

        self.py_jwt_layer = lambda_.LayerVersion.from_layer_version_arn(
            self,
            "py_jwt_layer",
            layer_version_arn=jwt_layer_arn[self.env_][self.region],
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
        env = {table.table_name: table.table_arn for (table, _) in tables or []}
        env["region_name"] = self.region_name
        env["prefix"] = self.prefix
        if queue:
            env["queue"] = queue.queue_url

        # create lambda function
        _lambda = lambda_.Function(
            self,
            id,
            function_name=f"{self.prefix}_{id}",
            runtime=lambda_.Runtime.PYTHON_3_10,
            code=lambda_.Code.from_asset("src"),
            handler=f"{id}.handler",
            environment=env,
            timeout=Duration.seconds(29),
            layers=layers or [],
        )
        add_tags(_lambda, {"lambda": id})

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
        path: str,
        http_method: str,
        resource_name: str,
        filename_overwrite: str = None,
        tables: List[Tuple[dynamodb.Table, Permission]] = None,
        buckets: List[Tuple[s3.Bucket, Permission]] = None,
        secrets: List[Tuple[str, sm.Secret]] = None,
        layers: List[lambda_.LayerVersion] = None,
        create_queue: bool = False,
    ) -> LambdaQueueTuple:
        resource = self.resources.get(path)

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
        if _queue:
            add_tags(_queue, {"queue": resource_name})

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
        resource.add_method(http_method, apigw.LambdaIntegration(_lambda))

        # grant lambda permission to read secret
        for secret_name, secret in secrets or []:
            secret.grant_read(_lambda)
            _lambda.add_environment(secret_name, secret.secret_name)

        return LambdaQueueTuple(_lambda, _queue)

    def create_cert_for_domain(self) -> acm.Certificate:
        cert = acm.Certificate(
            self,
            "Certificate",
            domain_name=f"*.{self.domain_name}",
            validation=acm.CertificateValidation.from_dns(self.hosted_zone),
        )
        add_tags(cert, {"cert": self.domain_name})

        return cert

    def create_api_gateway_and_lambdas(
        self,
    ) -> Tuple[apigw.RestApi, Dict[str, LambdaQueueTuple]]:
        # create resources
        api = apigw.RestApi(
            self,
            id=f"{self.prefix}_api",
            endpoint_types=[apigw.EndpointType.REGIONAL],
        )
        add_tags(api, {"api": f"{self.prefix}_api"})

        self.resources = RouteResource(
            resource=api.root,
            paths=[
                "/",
                "/sign-up",
                "/sign-in",
                "/api-keys",
                "/api-keys/{api_key}",
                "/credentials",
                "/credentials/{credential_name}",
                "/ml-models",
                "/ml-models/{model_name}",
            ],
        )

        if self.env_ == "dev":
            # set up custom domain
            domain_name = apigw.DomainName(
                self,
                f"{self.domain_name}_domain_name",
                mapping=api,
                certificate=self.main_cert,
                domain_name=f"{_USER_API}.{self.domain_name}",
            )

        # sign-up
        POST_signup = self.add(
            "/sign-up",
            "POST",
            "sign-up",
            filename_overwrite="signup_POST",
            tables=[(self.users, _READ_WRITE), (self.creds, _READ_WRITE)],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
            create_queue=True,
        )
        POST_signup.lambda_function.add_environment("domain_name", self.domain_name)
        POST_signup.lambda_function.add_environment(
            "hosted_zone_id", self.hosted_zone.hosted_zone_id
        )
        POST_signup.lambda_function.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(_ACM_FULL_PERMISSION_POLICY)
        )
        OPTIONS_signup = self.add(
            "/sign-up",
            "OPTIONS",
            "sign-up",
            filename_overwrite="signup_OPTIONS",
        )

        # sign-in
        POST_signin = self.add(
            "/sign-in",
            "POST",
            "sign-in",
            filename_overwrite="signin_POST",
            tables=[(self.users, _READ), (self.creds, _READ_WRITE)],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )
        OPTIONS_signin = self.add(
            "/sign-in",
            "OPTIONS",
            "sign-in",
            filename_overwrite="signin_OPTIONS",
        )

        # apikeys
        GET_list_of_api_keys = self.add(
            "/api-keys",
            "GET",
            "api-keys",
            filename_overwrite="api_keys_list_GET",
            tables=[
                (self.users, _READ),
                (self.creds, _READ),
                (self.usages, _READ),
                (self.models, _READ_WRITE),
            ],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )

        POST_api_keys = self.add(
            "/api-keys",
            "POST",
            "api-keys",
            filename_overwrite="api_keys_POST",
            tables=[
                (self.users, _READ),
                (self.creds, _READ),
                (self.usages, _READ),
                (self.models, _READ_WRITE),
            ],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )

        DELETE_api_keys = self.add(
            "/api-keys/{api_key}",
            "DELETE",
            "api-keys",
            filename_overwrite="api_keys_DELETE",
            tables=[
                (self.users, _READ),
                (self.creds, _READ),
                (self.usages, _READ),
                (self.models, _READ_WRITE),
            ],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )

        OPTIONS_api_keys_proxy = self.add(
            "/api-keys/{api_key}",
            "OPTIONS",
            "api-keys",
            filename_overwrite="api_keys_proxy_OPTIONS",
        )

        OPTIONS_api_keys = self.add(
            "/api-keys",
            "OPTIONS",
            "api-keys",
            filename_overwrite="api_keys_OPTIONS",
        )

        # credentials
        # Note: need read-write permission for GET due to use of PartiQL
        OPTIONS_credentials = self.add(
            "/credentials",
            "OPTIONS",
            "credentials",
            filename_overwrite="credentials_OPTIONS",
        )
        OPTIONS_proxy_credentials = self.add(
            "/credentials/{credential_name}",
            "OPTIONS",
            "credentials",
            filename_overwrite="credentials_proxy_OPTIONS",
        )
        GET_creds = self.add(
            "/credentials",
            "GET",
            "credentials",
            filename_overwrite="credentials_GET",
            tables=[(self.users, _READ), (self.creds, _READ_WRITE)],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )
        POST_access_creds = self.add(
            "/credentials",
            "POST",
            "credentials",
            filename_overwrite="credentials_POST",
            tables=[(self.users, _READ), (self.creds, _READ_WRITE)],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )
        DELETE_access_creds = self.add(
            "/credentials/{credential_name}",
            "DELETE",
            "credentials",
            filename_overwrite="credentials_DELETE",
            tables=[(self.users, _READ), (self.creds, _READ_WRITE)],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )

        # ml-models
        OPTIONS_ml_models = self.add(
            "/ml-models",
            "OPTIONS",
            "ml-models",
            filename_overwrite="ml_models_OPTIONS",
        )
        OPTIONS_ml_models_proxy = self.add(
            "/ml-models/{model_name}",
            "OPTIONS",
            "ml-models",
            filename_overwrite="ml_models_proxy_OPTIONS",
        )
        DELETE_ml_models = self.add(
            "/ml-models/{model_name}",
            "DELETE",
            "ml-models",
            filename_overwrite="ml_models_DELETE",
            tables=[
                (self.users, _READ),
                (self.creds, _READ),
                (self.models, _READ_WRITE),
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
            "/ml-models/{model_name}",
            "PUT",
            "ml-models",
            filename_overwrite="ml_models_PUT",
            tables=[
                (self.users, _READ),
                (self.creds, _READ),
                (self.models, _READ_WRITE),
            ],
            buckets=[(self.staging_bucket, _READ_WRITE)],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )
        PUT_ml_models.lambda_function.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                _APIGW_FULL_PERMISSION_POLICY
            )
        )

        POST_ml_models = self.add(
            "/ml-models/{model_name}",
            "POST",
            "ml-models",
            filename_overwrite="ml_models_POST",
            tables=[
                (self.users, _READ),
                (self.creds, _READ),
                (self.models, _READ_WRITE),
            ],
            buckets=[(self.staging_bucket, _READ_WRITE)],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )
        POST_ml_models.lambda_function.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                _APIGW_FULL_PERMISSION_POLICY
            )
        )

        GET_ml_models = self.add(
            "/ml-models/{model_name}",
            "GET",
            "ml-models",
            filename_overwrite="ml_models_GET",
            tables=[
                (self.users, _READ),
                (self.creds, _READ),
                (self.usages, _READ_WRITE),
                (self.models, _READ_WRITE),
            ],
            buckets=[(self.models_bucket, _READ)],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )

        GET_list_of_ml_models = self.add(
            "/ml-models",
            "GET",
            "ml-models",
            filename_overwrite="ml_models_list_GET",
            tables=[
                (self.users, _READ),
                (self.creds, _READ),
                (self.usages, _READ),
                (self.models, _READ_WRITE),
            ],
            secrets=[("jwt_secret", self.jwt_secret)],
            layers=[self.py_jwt_layer],
        )

        if self.env_ == "dev":
            # DNS records
            target = route53.CfnRecordSet.AliasTargetProperty(
                dns_name=domain_name.domain_name_alias_domain_name,
                hosted_zone_id=domain_name.domain_name_alias_hosted_zone_id,
                evaluate_target_health=False,
            )

            self.api_record = route53.CfnRecordSet(
                self,
                "UserApiARecord",
                name=f"{_USER_API}.{self.domain_name}",
                type="A",
                alias_target=target,
                hosted_zone_id=self.hosted_zone.hosted_zone_id,
                region=self.region_name,
                set_identifier=f"user-{cdk.Aws.STACK_NAME}",
            )

        return (
            api,
            {
                "POST_signup": POST_signup,
                "POST_signin": POST_signin,
                "GET_creds": GET_creds,
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
            runtime=lambda_.Runtime.PYTHON_3_10,
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
        add_tags(new_user_lambda, {"lambda": "new_user_lambda"})
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
            runtime=lambda_.Runtime.PYTHON_3_10,
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

        return delete_user_lambda

    def create_proxy_lambda(self) -> Tuple[lambda_.Alias, LambdaQueueTuple]:
        execution_lambda = lambda_.DockerImageFunction(
            self,
            "execution_lambda",
            function_name=f"{self.prefix}_execution",
            code=lambda_.DockerImageCode.from_ecr(
                repository=ecr.Repository.from_repository_name(
                    self,
                    "lambda_runtime_ecr",
                    "lambda_runtime" if self.env_ == "dev" else "neuro",
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
        add_tags(execution_lambda, {"lambda": "execution"})
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
            runtime=lambda_.Runtime.PYTHON_3_10,
            code=lambda_.Code.from_asset("src"),
            handler="proxy.handler",
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnets=self.subnets.subnets),
            timeout=Duration.seconds(30),
            environment={
                "region_name": self.region_name,
                "lambda": execution_alias.function_arn,
                "prefix": self.prefix,
            },
            security_groups=[self.sg],
        )
        add_tags(proxy_lambda, {"lambda": "proxy"})
        execution_alias.grant_invoke(proxy_lambda)
        self.models.grant_full_access(proxy_lambda)

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
        self.models_bucket.grant_read(proxy_lambda)
        self.logs_bucket.grant_read_write(proxy_lambda)

        # DynamoDB permission
        self.usages.grant_full_access(proxy_lambda)
        proxy_lambda.add_environment(self.usages.table_name, self.usages.table_arn)

        # SQS queue permission
        logs_queue.grant_send_messages(proxy_lambda)

        # Lambda Rest API
        proxy_api = apigw.LambdaRestApi(
            self,
            "proxy_api",
            handler=proxy_lambda,
            proxy=False,
            deploy=True,
            endpoint_types=[apigw.EndpointType.REGIONAL],
        )
        add_tags(proxy_api, {"api": "proxy_api"})
        username = proxy_api.root.add_resource("{username}")
        model_name = username.add_resource("{model_name}")
        model_name.add_method("GET")  # GET /{username}/{model_name}
        model_name.add_method("POST")  # POST /{username}/{model_name}

        if self.env_ == "dev":
            # Domain name
            domain_name = apigw.DomainName(
                self,
                f"{self.domain_name}_api_domain_name",
                mapping=proxy_api,
                certificate=self.main_cert,
                domain_name=f"api.{self.domain_name}",
            )

            # DNS records
            target = route53.CfnRecordSet.AliasTargetProperty(
                dns_name=domain_name.domain_name_alias_domain_name,
                hosted_zone_id=domain_name.domain_name_alias_hosted_zone_id,
                evaluate_target_health=False,
            )

            self.api_record = route53.CfnRecordSet(
                self,
                "ProxyApiARecord",
                name=f"api.{self.domain_name}",
                type="A",
                alias_target=target,
                hosted_zone_id=self.hosted_zone.hosted_zone_id,
                region=self.region_name,
                set_identifier=f"user-{cdk.Aws.STACK_NAME}",
            )
            add_tags(proxy_api, {"route53": self.domain_name})

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

    def create_s3_staging_trigger(self) -> lambda_.Function:
        # create lambda and have it triggered by
        # s3 bucket: self.staging_bucket
        # moving the file over to s3 bucket self.models_bucket
        # and log stuff in the dynamodb table self.models
        staging_trigger = lambda_.Function(
            self,
            "staging_trigger",
            function_name=f"{self.prefix}-staging-trigger",
            runtime=lambda_.Runtime.PYTHON_3_10,
            code=lambda_.Code.from_asset("src"),
            handler="s3_staging_trigger.handler",
            environment={
                "prefix": self.prefix,
            },
            timeout=Duration.seconds(29),
        )
        self.staging_bucket.grant_read_write(staging_trigger)
        self.models_bucket.grant_read_write(staging_trigger)
        self.models.grant_full_access(staging_trigger)

        staging_trigger.add_event_source(self.staging_s3_trigger)

        return staging_trigger

    def create_staging_bucket(self):
        self.staging_bucket = s3.Bucket(
            self,
            f"{self.prefix}_staging",
            bucket_name=f"{self.prefix}-staging-{self.region_name}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        self.staging_s3_trigger = event_sources.S3EventSource(
            self.staging_bucket, events=[s3.EventType.OBJECT_CREATED]
        )

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        prefix: str,
        domain_name: str,
        region_name: str,
        other_regions: List[str],
        account_number: str,
        buckets: Dict[str, s3.Bucket],
        vpc: ec2.Vpc,
        env_: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_ = env_
        self.account_number = account_number
        self.prefix = prefix
        self.region_name = region_name
        self.domain_name = domain_name

        self.models_bucket = buckets["models_bucket"]
        self.logs_bucket = buckets["models_bucket"]
        self.create_staging_bucket()

        self.vpc = vpc
        self.subnets = self.vpc.select_subnets(
            subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
        )

        # Imports
        self.import_secrets()
        self.import_lambda_layers()
        self.import_databases()

        # DNS
        self.hosted_zone = self.import_hosted_zone()
        self.main_cert = self.create_cert_for_domain()

        # ECR
        repo_name = "lambda_runtime" if self.env_ == "dev" else "neuro"
        ecr = boto3.Session(
            profile_name="dev",
            region_name=self.region_name,
        ).client("ecr")
        self.lambda_image_digest = next(
            image["imageDigest"]
            for image in ecr.list_images(repositoryName=repo_name)["imageIds"]
            if image.get("imageTag", "") == "latest"
        )

        # security group for proxy lambda & execution lambda
        self.sg = self.create_security_group()

        # proxy lambda + logs queue
        self.execution_alias, self.proxy = self.create_proxy_lambda()

        # API Gateway and lambda-integrated routes
        self.api, rest = self.create_api_gateway_and_lambdas()
        self.POST_signup = rest["POST_signup"]
        self.POST_signin = rest["POST_signin"]
        self.GET_creds = rest["GET_creds"]
        self.PUT_ml_models = rest["PUT_ml_models"]
        self.GET_ml_models = rest["GET_ml_models"]
        self.GET_list_of_ml_models = rest["GET_list_of_ml_models"]
        self.DELETE_ml_models = rest["DELETE_ml_models"]

        # Additional lambdas
        self.new_user_lambda = self.create_new_user_lambda()
        self.delete_user_lambda = self.create_delete_user_lambda()

        # Trigger lambda when new file is uploaded to staging bucket
        self.staging_trigger = self.create_s3_staging_trigger()

        # SNS + SQS and add SQS queue as event source for lambda
        self.regional_topic = sns.Topic(
            self,
            "container",
            display_name=f"{prefix}_container_display",
            topic_name=f"{prefix}_container_topic",
        )
        self.regional_queue = sqs.Queue(
            self,
            "regional_queue",
            visibility_timeout=Duration.minutes(15),
            retention_period=Duration.hours(12),
        )
        self.regional_topic.add_subscription(
            sns_subs.SqsSubscription(self.regional_queue)
        )
        self.staging_trigger.add_event_source(
            event_sources.SqsEventSource(self.regional_queue)
        )
        self.staging_trigger.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(_SNS_FULL_PERMISSION_POLICY)
        )
        # record arn of other regions' SNS topic as enviornment variable
        self.staging_trigger.add_environment("topic_arn", self.regional_topic.topic_arn)
        self.staging_trigger.add_environment("region_0", self.region_name)
        for k, region in enumerate(other_regions):
            self.staging_trigger.add_environment(f"region_{k+1}", region)
