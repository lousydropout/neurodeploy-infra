import requests

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VybmFtZSI6InZpbmNlbnQiLCJleHAiOjE2ODMwNDg1MjF9.M4Z1f94KWO1BzgXEZ5o_kIeQJAWULpw-PoA88Y6BACc"
model_name = "model1"
model_type = "tensorflow"
persistence_type = "h5"
is_public = False

# Create model
http_response = requests.put(
    url=(
        f"https://user-api.playingwithml.com/ml-models/{model_name}"
        f"?lib={model_type}"
        f"&filetype={persistence_type}"
        f"&is_public={is_public}"
    ),
    headers={"Authorization": f"Bearer {token}"},
)
x = http_response.json()

# Upload h5 file to update mode
# Assumes: there is a 'model.h5' file in this directory
response = requests.post(
    x["url"], data=x["fields"], files={"file": open("model.h5", "rb")}
)

print(response.status_code)
