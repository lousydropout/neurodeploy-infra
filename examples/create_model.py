import requests
from pprint import pprint

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VybmFtZSI6ImxvdXN5ZHJvcG91dCIsImV4cCI6MTY4MzEzMzg5Mn0.-hkfbVulnTRvNYaf_5EbLKjcKgx0KbFVQK-D57WD_sU"
domain_name = "neurodeploy"
model_name = "abc"
model_type = "tensorflow"
persistence_type = "h5"
is_public = False

# Create model
http_response = requests.put(
    url=(
        f"https://user-api.{domain_name}.com/ml-models/{model_name}"
        f"?lib={model_type}"
        f"&filetype={persistence_type}"
        f"&is_public={is_public}"
    ),
    headers={"Authorization": f"Bearer {token}"},
)
x = http_response.json()
pprint(x)

# Upload h5 file to update mode
# Assumes: there is a 'model.h5' file in this directory
response = requests.post(
    x["url"], data=x["fields"], files={"file": open("model.h5", "rb")}
)

print(response.status_code)
