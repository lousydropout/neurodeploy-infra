import os
import json
from time import sleep
import boto3

acm = boto3.client("acm")
apigw = boto3.client("apigateway")
route53 = boto3.client("route53")

hosted_zone_id = os.environ["hosted_zone_id"]

waiter = acm.get_waiter("certificate_validated")


def create_api_for_sub_domain(domain_name: str, sub: str) -> dict:
    record = {"success": False, "step": 0}
    # 1. request cert
    print(f"Requesting certicate for {sub}.{domain_name}", end=". . . ")
    cert_request = acm.request_certificate(
        DomainName=f"{sub}.{domain_name}",
        ValidationMethod="DNS",
    )
    print("done")

    cert_arn = cert_request["CertificateArn"]
    print("cert arn: ", cert_arn)
    cert = {"Certificate": {}}
    while "Value" not in (
        cert["Certificate"]
        .get("DomainValidationOptions", [{}])[0]
        .get("ResourceRecord", {})
    ):
        cert = acm.describe_certificate(CertificateArn=cert_arn)
        print("cert: ", json.dumps(cert, default=str))
        sleep(0.2)
    val = cert["Certificate"]["DomainValidationOptions"][0]
    resource_record = val["ResourceRecord"]

    record = {"success": True, "step": 1, "resources": {"cert": cert_arn}}
    print("record 1: ", json.dumps(record, default=str))

    # 2. create dns CNAME record for validation
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
    response = route53.change_resource_record_sets(
        HostedZoneId=hosted_zone_id,
        ChangeBatch={"Changes": dns_validation_records},
    )

    record = {
        "success": True,
        "step": 2,
        "resources": {"route53 validation record": cert_arn},
    }
    print("record 2: ", json.dumps(record, default=str))

    # 3. create apigw
    api = apigw.create_rest_api(
        name=f"{domain_name}-{sub}-api",
        endpointConfiguration={"types": ["REGIONAL"]},
    )
    api_id = api["id"]

    record = {
        "success": True,
        "step": 3,
        "resources": {"api gateway id": api_id},
    }
    print("record 3: ", json.dumps(record, default=str))

    # 2b Wait until cert is issued
    print("Waiting for ceritifcate to be validated", end=". . .")
    waiter.wait(
        CertificateArn=cert_arn, WaiterConfig={"Delay": 10, "MaxAttempts": 6 * 3}
    )
    print("done")

    # 4. create custom domain for apigw
    custom_domain = apigw.create_domain_name(
        domainName=f"{sub}.{domain_name}",
        regionalCertificateName=f"{sub}.{domain_name}",
        regionalCertificateArn=cert_arn,
        endpointConfiguration={"types": ["REGIONAL"]},
        tags={"string": "string"},
        securityPolicy="TLS_1_2",
    )
    apigw_domain_name = custom_domain["regionalDomainName"]
    apigw_zone_id = custom_domain["regionalHostedZoneId"]

    record = {
        "success": True,
        "step": 4,
        "resources": {
            "apigw_domain_name": apigw_domain_name,
            "apigw_zone_id": apigw_zone_id,
        },
    }
    print("record 4: ", json.dumps(record, default=str))

    # 5. get root resource
    response = apigw.get_resources(restApiId=api_id)
    resources = response["items"]
    root_id = list(filter(lambda x: x["path"] == "/", resources))[0]["id"]

    record = {"success": True, "step": 5, "resources": {"root_id": root_id}}
    print("record 5: ", json.dumps(record, default=str))

    # 6. create resource
    ping = apigw.create_resource(
        restApiId=api_id,
        parentId=root_id,
        pathPart="ping",
    )
    ping_id = ping["id"]

    record = {"success": True, "step": 6, "resources": {"ping_id": ping_id}}
    print("record 6: ", json.dumps(record, default=str))

    # 7. create method (requires resource)
    GET_ping = apigw.put_method(
        restApiId=api_id,
        resourceId=ping_id,
        httpMethod="GET",
        authorizationType="NONE",
    )

    # 8. create integration
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

    ping_method_response = apigw.put_method_response(
        restApiId=api_id,
        resourceId=ping_id,
        httpMethod="GET",
        statusCode="200",
    )

    # 9. create deployment (apigw mush contain method)
    deployment = apigw.create_deployment(
        restApiId=api_id,
        stageName="prod",
        tracingEnabled=False,
    )

    # 10. associate custom domain w/ apigw
    response = apigw.create_base_path_mapping(
        domainName=f"{sub}.{domain_name}",
        restApiId=api_id,
        stage="prod",
    )

    record = {"success": True, "step": 10, "resources": {"base path mapping": response}}
    print("record 10: ", json.dumps(record, default=str))

    # 11. update route53 to point {sub}.{domain_name}
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
    response = route53.change_resource_record_sets(
        HostedZoneId=hosted_zone_id,
        ChangeBatch={"Changes": subdomain_records},
    )

    record = {
        "success": True,
        "step": 11,
        "resources": {"dns record for sub domain": response},
    }
    print("record 11: ", json.dumps(record, default=str))

    # route53_resources = route53.list_resource_record_sets(
    #     HostedZoneId=hosted_zone_id,
    #     StartRecordName=f"{sub}.{domain_name}",
    #     StartRecordType="A",
    # )

    return {
        "endpoint": f"https://{sub}.{domain_name}",
    }
