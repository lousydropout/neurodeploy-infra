import json
from helpers import dynamodb as ddb
import boto3

# dynamodb boto3
_APIS_TABLE_NAME = "neurodeploy_Apis"
dynamodb_client = boto3.client("dynamodb")

# other boto3 clients
acm = boto3.client("acm")
apigw = boto3.client("apigateway")
route53 = boto3.client("route53")


def get_record(username: str) -> dict:
    response = dynamodb_client.get_item(
        TableName=_APIS_TABLE_NAME,
        Key=ddb.to_({"pk": username, "sk": "default"}),
    )
    item = ddb.from_(response.get("Item", {}))
    return item


def delete_record(username: str):
    key = ddb.to_({"pk": username, "sk": "default"})
    try:
        dynamodb_client.delete_item(TableName=_APIS_TABLE_NAME, Key=key)
    except dynamodb_client.exceptions.ResourceNotFoundException:
        print(f"Item {key} was already deleted.")


def delete_resources(
    username: str,
    domain_name: str,
    rest_api_id: str,
    hosted_zone_id: str,
    cert_arn: str,
    dns_validation_record: str,
    custom_domain_a_record: str,
):
    record = {
        "custom_domain": True,
        "dns_validation": True,
        "a_record_for_sub_domain": True,
        "cert_for_sub_domain": True,
        "api_gateway": True,
    }

    # delete custom domain
    # can get a "too many requests" error
    try:
        if domain_name:
            apigw.delete_domain_name(domainName=domain_name)
    except apigw.exceptions.NotFoundException as err:
        print(f"Custom domain {domain_name} was already deleted: {err}")
    except Exception as err:
        print(f"Custom domain {domain_name} deletion error: ", err)
        record["custom_domain"] = False
    else:
        print(f"Deleted API Gateway custom domain '{domain_name}'")

    # delete validation record in route 53
    try:
        if dns_validation_record:
            response = route53.change_resource_record_sets(
                HostedZoneId=hosted_zone_id,
                ChangeBatch={"Changes": json.loads(dns_validation_record)},
            )
    except route53.exceptions.NoSuchHostedZone as err:
        print(f"The route 53 hosted zone '{hosted_zone_id}' does not exist")
    except route53.exceptions.InvalidChangeBatch as err:
        if "it was not found" not in str(err):
            raise err
        print(f"The Route 53 validation record was already deleted")
    except Exception as err:
        print("DNS validation record deletion error: ", err)
        record["dns_validation"] = False
    else:
        print("Deleted validation record in route 53")

    # delete custom domain in route 53
    try:
        if custom_domain_a_record:
            response = route53.change_resource_record_sets(
                HostedZoneId=hosted_zone_id,
                ChangeBatch={"Changes": json.loads(custom_domain_a_record)},
            )
    except route53.exceptions.NoSuchHostedZone as err:
        print(f"The route 53 hosted zone '{hosted_zone_id}' does not exist")
    except route53.exceptions.InvalidChangeBatch as err:
        if "it was not found" not in str(err):
            raise err
        print(f"The Route 53 custom domain record was already deleted")
    except Exception as err:
        print("Route 53 A record for sub domain deletion error: ", err)
        record["a_record_for_sub_domain"] = False
    else:
        print("Deleted A record for custom domain in route 53")

    # delete cert
    try:
        if cert_arn:
            response = acm.delete_certificate(CertificateArn=cert_arn)
    except acm.exceptions.ResourceNotFoundException as err:
        print(f"Certificate '{cert_arn}' has already been deleted.")
    except acm.exceptions.ResourceInUseException as err:
        print(f"Certificate '{cert_arn}' is currently still in use: {err}")
        record["cert_for_sub_domain"] = False
    except Exception as err:
        print(f"Certificate '{cert_arn}' for sub domain deletion error: ", err)
        record["cert_for_sub_domain"] = False
    else:
        print(f"Deleted cert '{cert_arn}'")

    # delete apigw
    try:
        if rest_api_id:
            response = apigw.delete_rest_api(restApiId=rest_api_id)
    except apigw.exceptions.NotFoundException as err:
        print(f"API Gateway '{rest_api_id}' was already deleted: {err}")
    except Exception as err:
        print(f"API Gateway '{rest_api_id}' deletion error: ", err)
        record["api_gateway"] = False
    else:
        print(f"Deleted rest api '{rest_api_id}'")

    # delete record
    if all(val for val in record.values()):
        try:
            delete_record(username)
        except:
            print("Potentially failed to delete record")
        else:
            print("Record deleted")

    # Log sumamry
    print("Deletion summary: ", json.dumps(record, default=str))
