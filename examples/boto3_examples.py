# example
import boto3

apigw = boto3.client("apigateway")
route53 = boto3.route53("client")

domain_name = "playingwithml.com"
region = "us-west-2"
hostd_zone_id = "Z045768230VQTC2FR2CAN"
# apigw_dns_name = "d-bp30zd3984.execute-api.us-west-2.amazonaws.com"

# # get the regional api domain name for a given "domain_name"
# response = apigw.get_domain_names(
#     # position='string',
#     limit=500
# )
# apigw_dns_name = [
#     x["regionalDomainName"]
#     for x in response["items"]
#     if x["domainName"] == f"api.{domain_name}"
# ][0]

# # update route 53 --
# response = route53.change_resource_record_sets(
#     HostedZoneId=hostd_zone_id,
#     ChangeBatch={
#         "Changes": [
#             {
#                 "Action": "CREATE",
#                 "ResourceRecordSet": {
#                     "Name": f"api.{domain_name}",
#                     "Type": "A",
#                     "Region": region,
#                     "AliasTarget": {
#                         "HostedZoneId": hostd_zone_id,
#                         "DNSName": apigw_dns_name,
#                         "EvaluateTargetHealth": True,
#                     },
#                 },
#             },
#         ]
#     },
# )


# create API Gateway
response = apigw.create_rest_api(
    name="testAPI", endpointConfiguration={"types": ["REGIONAL"]}
)


# create Certificate for sub-domain
# route53 = boto3.client('route53')
acm = boto3.client("acm")

sub = "vincent-api"
response = acm.request_certificate(
    DomainName=f"{sub}.{domain_name}", ValidationMethod="DNS", KeyAlgorithm="RSA_2048"
)
cert_arn = response["CertificateArn"]

# describe cert to get the validation record set
cert = acm.describe_certificate(CertificateArn=cert_arn)
val = cert["Certificate"]["DomainValidationOptions"][0]
resource_record = val["ResourceRecord"]
val_name = resource_record["Name"]
val_val = resource_record["Value"]

# create CNAME record for cert validation
response = route53.change_resource_record_sets(
    HostedZoneId=hostd_zone_id,
    ChangeBatch={
        "Changes": [
            {
                "Action": "CREATE",
                "ResourceRecordSet": {
                    "Name": val_name,
                    "Type": "CNAME",
                    "TTL": 300,
                    "ResourceRecords": [{"Value": val_val}],
                },
            }
        ]
    },
)
