import json
import boto3
from botocore.exceptions import ClientError


def get_secret(secret_name: str, region_name: str) -> dict[str, str]:
    # Create a Secrets Manager client
    client = boto3.client("secretsmanager", region_name=region_name, use_ssl=True)

    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    # Decrypts secret using the associated KMS key.
    secret = get_secret_value_response["SecretString"]

    # Your code goes here.
    return json.loads(secret)
