# Deploy a semantic search in GCP

The deployment is divided in two parts:
* The creation of the cluster with Terraform
* The deployment of all the services with Helm

Before to start be sure to have all the proper tools installed:
* Cloud SDK: [here](https://cloud.google.com/sdk/docs/install)
* Terraform: [here](https://learn.hashicorp.com/tutorials/terraform/install-cli)
* Helm: [here](https://helm.sh/docs/intro/install/)
* Kubectl: [here](https://kubernetes.io/fr/docs/tasks/tools/install-kubectl/)

## Create the cluster

Terraform allows to easily create a cluster per environment, here we will create one for a `dev` environment and another one for a `prod` environment.

### Dev environment

First of all, rename the `dev.examples.tfvars` into `dev.tfvars` with:
```
mv dev.examples.tfvars dev.tfvars
```

Once done you can fullfil all the variables in it accordingly to the GCP settings you want:
* `project_id`: The GCP project ID that will host the cluster.
* `region`: The region that will host the cluster.
* `zones`: The zone that will host the cluster (required if you want a zonal cluster). Must be a list.
* `network`: The name of the VPC network used by the cluster.
* `subnetwork`: The name of the subnetwork used by the VPC.
* `ip_range_pods_name`: The name of the secondary ip range to use for the pods.
* `ip_range_services_name`: The name of the secondary ip range to use for the services.
* `compute_engine_service_account`: The name of the service account to associate to each node in the cluster.

Once all these values filled, we can create the `dev` workspace and set it up with the following commands:
```
terraform workspace new dev
terraform init
```

Finally, the last step is to create the cluster with:
```
terraform apply -var-file=dev.tfvars
```

### Prod environment

The exact same logic than for the `dev` must be applied to deploy a `prod` environment, just replace `dev.tfvars` with `prod.tfvars`. If you need to switch from one environment to another you can run:
```
terraform workspace select <ENV_NAME>
```
By replacing `<ENV_NAME>` with `dev` or `prod` depending if you want to switch from `dev` to `prod` or the opposite.

## Deploy the semantic search service
