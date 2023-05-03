# User-API

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
