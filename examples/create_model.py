import requests

MODELS_S3_BUCKET = "neurodeploy-models-us-west-1"


token = ""
model_name = ""
model_type = "tensorflow"
persistence_type = "h5"

# Create model
http_response = requests.put(
    url=f"https://user-api.playingwithml.com/ml-models/{model_name}?model_type={model_type}&persistence_type={persistence_type}",
    headers={"Authorization": f"Bearer {token}"},
)
x = http_response.json()

# Upload h5 file to update mode
# Assumes: there is a 'model.h5' file in this directory
response = requests.post(
    x["url"], data=x["fields"], files={"file": open("model.h5", "rb")}
)

print(response.status_code)
