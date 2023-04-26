import requests

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VybmFtZSI6InZpbmNlbnQiLCJleHAiOjE2ODI2MTM0NzJ9.VhAE0u5YNFj1VTKZsW0IQKD-odI6y4Cbb03nnzHZ5xA"
model_name = "model1"
model_type = "tensorflow"
persistence_type = "h5"

# Create model
http_response = requests.put(
    url=f"https://user-api.playingwithml.com/ml-models/{model_name}?lib={model_type}&filetype={persistence_type}",
    headers={"Authorization": f"Bearer {token}"},
)
x = http_response.json()

# Upload h5 file to update mode
# Assumes: there is a 'model.h5' file in this directory
response = requests.post(
    x["url"], data=x["fields"], files={"file": open("model.h5", "rb")}
)

print(response.status_code)
