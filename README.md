# User-API

## Status

Currently, the stacks are only deployed to a single region each.

- `prod` is deployed in `us-west-1`
- `dev` is deployed in `us-east-1`

## Installation

#### Setup virtual environment

```bash
python -m venv .venv
```

#### Activate virtual environment

```bash
source .venv/bin/activate
```

#### Install required python libraries

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

## Prod deployment

```bash
./deploy/base_stack     # deploys the Global dynamodb tables to us-west-1 and us-east-2
./deploy/regional/east  # deploys VPC to us-east-2
./deploy/regional/west  # deploys VPC to us-west-1
./deploy/main/east      # deploys the main stack to us-east-2
./deploy/main/west      # deploys the main stack to us-west-1
```

## Dev deployment

```bash
./deploy-dev/base_stack     # deploys the Global dynamodb tables to us-east-1
./deploy-dev/regional/east  # deploys VPC to us-east-1
./deploy-dev/regional/west  # deploys VPC to us-west-1
./deploy-dev/main/east      # deploys the main stack to us-east-1
./deploy-dev/main/west      # deploys the main stack to us-west-1
```
