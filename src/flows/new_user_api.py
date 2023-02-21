import os
import json
from time import sleep
from helpers import dynamodb as ddb
import boto3

_ERROR_429 = (
    "429 error when attempting to create API Gateway domain name. Sleep 10 seconds."
)

# dynamodb boto3
dynamodb_client = boto3.client("dynamodb")
dynamodb = boto3.resource("dynamodb")
_APIS_TABLE_NAME = "neurodeploy_Apis"
_API_TABLE = dynamodb.Table(_APIS_TABLE_NAME)

# other boto3 clients
acm = boto3.client("acm")
apigw = boto3.client("apigateway")
route53 = boto3.client("route53")

# acm waiter
hosted_zone_id = os.environ["hosted_zone_id"]
waiter = acm.get_waiter("certificate_validated")


def write_object(username: str, payload: dict):
    record = {"pk": username, "sk": "default", **payload}
    _API_TABLE.put_item(Item=record)


def get_record(username: str) -> dict:
    key = ddb.to_({"pk": username, "sk": "default"})
    response = dynamodb_client.get_item(TableName=_APIS_TABLE_NAME, Key=key)
    return ddb.from_(response.get("Item", {}))


def request_cert(record: dict) -> str:
    username = record["username"]
    sub = username
    domain_name = record["domain_name"]

    print(f"1. Requesting certicate for {sub}.{domain_name}")
    cert_request = acm.request_certificate(
        DomainName=f"{sub}.{domain_name}",
        ValidationMethod="DNS",
    )

    cert_arn = cert_request["CertificateArn"]

    record["step"] = 1
    record["resources"]["cert_arn"] = cert_arn
    print("record 1: ", json.dumps(record, default=str))
    write_object(username, record)
    return cert_request["CertificateArn"]


def wait_for_validation_values(cert_arn: str) -> dict:
    iter, cert = 1, {"Certificate": {}}
    while "Value" not in (
        cert["Certificate"]
        .get("DomainValidationOptions", [{}])[0]
        .get("ResourceRecord", {})
    ):
        print("iter: ", iter)
        iter += 1
        cert = acm.describe_certificate(CertificateArn=cert_arn)
        sleep(0.2)

    print("cert: ", json.dumps(cert, default=str))

    # return values
    return cert["Certificate"]["DomainValidationOptions"][0]["ResourceRecord"]


def create_vaidation_record(record: dict, resource_record: dict):
    username = record["username"]
    dns_validation_records = [
        {
            "Action": "CREATE",
            "ResourceRecordSet": {
                "Name": resource_record["Name"],
                "Type": "CNAME",
                "TTL": 300,
                "ResourceRecords": [
                    {"Value": resource_record["Value"]},
                ],
            },
        },
    ]
    try:
        _ = route53.change_resource_record_sets(
            HostedZoneId=hosted_zone_id,
            ChangeBatch={"Changes": dns_validation_records},
        )
    except route53.exceptions.InvalidChangeBatch as err:
        if "it already exists" in str(err):
            print("Validation record already exists")
        else:
            raise err

    dns_validation_records[0]["Action"] = "DELETE"
    record["step"] = 2
    record["resources"]["dns_validation_record"] = json.dumps(dns_validation_records)
    write_object(username, record)


def create_api(record: dict) -> str:
    domain_name = record["domain_name"]
    username = record["username"]
    sub = username

    # create api
    api = apigw.create_rest_api(
        name=f"{domain_name}-{sub}-api",
        endpointConfiguration={"types": ["REGIONAL"]},
    )

    api_id = api["id"]
    record["step"] = 3
    record["resources"]["rest_api_id"] = api_id
    write_object(username, record)

    # 4. get root resource
    response = apigw.get_resources(restApiId=api_id)
    resources = response["items"]
    root_id = list(filter(lambda x: x["path"] == "/", resources))[0]["id"]

    ping = apigw.create_resource(
        restApiId=api_id,
        parentId=root_id,
        pathPart="ping",
    )
    ping_id = ping["id"]

    # 6. create method (requires resource)
    GET_ping = apigw.put_method(
        restApiId=api_id,
        resourceId=ping_id,
        httpMethod="GET",
        authorizationType="NONE",
    )

    # 7. create integration
    ping_integration = apigw.put_integration(
        restApiId=api_id,
        resourceId=ping_id,
        httpMethod="GET",
        integrationHttpMethod="PUT",
        type="MOCK",
        requestTemplates={"application/json": json.dumps({"statusCode": 200})},
    )

    # 8. create integration response
    GET_ping_response = apigw.put_integration_response(
        restApiId=api_id,
        resourceId=ping_id,
        httpMethod="GET",
        statusCode="200",
        responseTemplates={},
    )

    # 9. create method response
    ping_method_response = apigw.put_method_response(
        restApiId=api_id,
        resourceId=ping_id,
        httpMethod="GET",
        statusCode="200",
    )

    # 10. create deployment (apigw mush contain method)
    deployment = apigw.create_deployment(
        restApiId=api_id,
        stageName="prod",
        tracingEnabled=False,
    )

    return api_id


def create_custom_domain(record: dict, cert_arn: str, api_id: str) -> dict:
    domain_name = record["domain_name"]
    username = record["username"]
    sub = username

    while True:
        try:
            custom_domain = apigw.create_domain_name(
                domainName=f"{sub}.{domain_name}",
                regionalCertificateName=f"{sub}.{domain_name}",
                regionalCertificateArn=cert_arn,
                endpointConfiguration={"types": ["REGIONAL"]},
                tags={"username": username},
                securityPolicy="TLS_1_2",
            )
            break
        except apigw.exceptions.BadRequestException as err:
            _already_exists = "The domain name you provided already exists."
            if _already_exists not in str(err):
                raise err
            custom_domain = apigw.get_domain_name(domainName=f"{sub}.{domain_name}")
            break
        except apigw.exceptions.TooManyRequestsException as err:
            print(_ERROR_429)
            sleep(10)

    record["step"] = 5
    record["resources"]["domain_name"] = f"{sub}.{domain_name}"
    print("record 5: ", json.dumps(record, default=str))
    write_object(username, record)

    # associate custom domain w/ apigw
    try:
        _ = apigw.create_base_path_mapping(
            domainName=f"{sub}.{domain_name}",
            restApiId=api_id,
            stage="prod",
        )
    except apigw.exceptions.BadRequestException as err:
        _already_exists = "The domain name you provided already exists."
        if _already_exists not in str(err):
            raise err

    return custom_domain


def create_a_record(record: dict, custom_domain: dict):
    domain_name = record["domain_name"]
    username = record["username"]
    sub = username

    apigw_domain_name = custom_domain["regionalDomainName"]
    apigw_zone_id = custom_domain["regionalHostedZoneId"]

    subdomain_records = [
        {
            "Action": "CREATE",
            "ResourceRecordSet": {
                "Name": f"{sub}.{domain_name}",
                "Type": "A",
                "AliasTarget": {
                    "HostedZoneId": apigw_zone_id,
                    "DNSName": apigw_domain_name,
                    "EvaluateTargetHealth": True,
                },
            },
        },
    ]
    try:
        _ = route53.change_resource_record_sets(
            HostedZoneId=hosted_zone_id,
            ChangeBatch={"Changes": subdomain_records},
        )
    except route53.exceptions.InvalidChangeBatch as err:
        if "it already exists" in str(err):
            print("Route 53 A record already exists")
        else:
            raise err

    subdomain_records[0]["Action"] = "DELETE"
    record["step"] = 7
    record["resources"]["custom_domain_a_record"] = json.dumps(subdomain_records)
    print("record 7: ", json.dumps(record, default=str))
    write_object(username, record)


def wait_for_cert_to_be_issued(cert_arn: str):
    print("Waiting for ceritifcate to be validated", end=". . .")
    waiter.wait(CertificateArn=cert_arn, WaiterConfig={"Delay": 30, "MaxAttempts": 6})
    print("done")
    sleep(30)


def create_api_for_sub_domain(domain_name: str, username: str) -> dict:
    sub = username

    # 0. get record
    record = get_record(username)
    if not record:
        record = {
            "domain_name": domain_name,
            "username": username,
            "success": False,
            "step": 0,
            "resources": {"hosted_zone_id": hosted_zone_id},
        }

    # 1. request cert
    if "cert_arn" in record["resources"]:
        cert_arn = record["resources"]["cert_arn"]
    else:
        cert_arn = request_cert(record)

    # 2. create dns CNAME record for validation
    if "dns_validation_record" not in record["resources"]:
        resource_record = wait_for_validation_values(cert_arn)
        create_vaidation_record(record, resource_record)

    # 3. create apigw and GET /ping
    if "rest_api_id" in record["resources"]:
        api_id = record["resources"]["rest_api_id"]
    else:
        api_id = create_api(record)

    # 4. Wait until cert is issued
    wait_for_cert_to_be_issued(cert_arn)

    # 5. create custom domain for apigw and point to api
    if "custom_domain" in record["resources"]:
        custom_domain = record["resources"]["custom_domain"]
    else:
        custom_domain = create_custom_domain(record, cert_arn, api_id)

    # 6. update route 53 to point {sub}.{domain_name}
    if "a_record_for_sub_domain" not in record["resources"]:
        create_a_record(record, custom_domain)

    return {
        "endpoint": f"https://{sub}.{domain_name}",
    }
