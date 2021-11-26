# A semantic search in GCP

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
* `project_id`: the GCP project ID that will host the cluster.
* `region`: the region that will host the cluster.
* `zones`: the zone that will host the cluster (required if you want a zonal cluster). Must be a list.
* `network`: the name of the VPC network used by the cluster.
* `subnetwork`: the name of the subnetwork used by the VPC.
* `ip_range_pods_name`: the name of the secondary ip range to use for the pods.
* `ip_range_services_name`: the name of the secondary ip range to use for the services.
* `compute_engine_service_account`: the name of the service account to associate to each node in the cluster.
* `triton_machine_type`: the GCP machine type for the Triton Server node pool. A list is available in the [GCP documentation](https://cloud.google.com/compute/docs/machine-types).
* `triton_min_cpu_platform`: the targeted min CPU platform for the Triton Server node pool. A list is available in the [GCP documentation](https://cloud.google.com/compute/docs/instances/specify-min-cpu-platform).
* `triton_disk_size_gb`: the disk size for the Triton Server node pool.
* `faiss_machine_type`: the GCP machine type for the FAISS Server node pool. A list is available in the [GCP documentation](https://cloud.google.com/compute/docs/machine-types).
* `faiss_min_cpu_platform`: the targeted min CPU platform for the FAISS Server node pool. A list is available in the [GCP documentation](https://cloud.google.com/compute/docs/instances/specify-min-cpu-platform).
* `faiss_disk_size_gb`: the disk size for the FAISS Server node pool.
* `orchestration_machine_type`: the GCP machine type for the Orchestration node pool. A list is available in the [GCP documentation](https://cloud.google.com/compute/docs/machine-types).
* `orchestration_min_cpu_platform`: the targeted min CPU platform for the Orchestration node pool. A list is available in the [GCP documentation](https://cloud.google.com/compute/docs/instances/specify-min-cpu-platform).
* `orchestration_disk_size_gb`: the disk size for the Orchestration node pool.
* `elasticsearch_machine_type`: the GCP machine type for the Elasticsearch node pool. A list is available in the [GCP documentation](https://cloud.google.com/compute/docs/machine-types).
* `elasticsearch_min_cpu_platform`: the targeted min CPU platform for the Elasticsearch node pool. A list is available in the [GCP documentation](https://cloud.google.com/compute/docs/instances/specify-min-cpu-platform).
* `elasticsearch_disk_size_gb`: the disk size for the Elasticsearch node pool.

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

## Deploy the services

The deployment is divided is three parts:
* Triton Server to handle the model inference
* FAISS Server to handle the FAISS index
* Search Orchestration as the front API

### Deploy Triton Server

Each environment (`dev` and `prod`) will contain the same Triton service. Let's start with `dev`.

#### Dev environment

Connect your `gcloud` command to the `dev` cluster with:
```
gcloud container clusters get-credentials <DEV_CLUSTER_NAME> --region <DEV_CLUSTER_REGION>
```

With:
* `<DEV_CLUSTER_NAME>`: the name of the `dev` cluster. Should be `<project_id>-dev-cluster` with `<project_id>` the name filled in the `dev.tfvars` file.
* `<DEV_CLUSTER_REGION>`: the region filled in the `dev.tfvars` file.

Next, deploy Prometheus and Grafana with:
```
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install metrics --set nodeSelector."cloud\\.google\\.com/gke-nodepool"=pool-tritonserver --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false prometheus-community/kube-prometheus-stack
```

In order to deploy the Triton Server, you have to rename the `values` YAML files with:
```
mv tritonserver/values-dev.examples.yaml tritonserver/values-dev.yaml
```

Once done you can fullfil all the variables in it accordingly to the Triton Server settings you want:
* `modelRepositoryPath`: the GCS address of your model repository.
* `numGpus`: the number of GPUs used by Triton.
* `nproc`: the number of vCPUs used by Triton.

Finally, deploy the Triton Server Helm chart:
```
helm install tritonserver ./tritonserver -f tritonserver/values-dev.yaml
```

#### Prod environment

The exact same logic than for the `dev` must be applied to deploy in the `prod` environment:
```
gcloud container clusters get-credentials <PROD_CLUSTER_NAME> --region <PROD_CLUSTER_REGION>
helm install metrics --set nodeSelector."cloud\\.google\\.com/gke-nodepool"=pool-tritonserver --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false prometheus-community/kube-prometheus-stack
mv tritonserver/values-prod.examples.yaml tritonserver/values-prod.yaml
helm install tritonserver ./tritonserver -f tritonserver/values-prod.yaml
```

### Deploy FAISS Server

Each environment (`dev` and `prod`) will contain the same FAISS service. Let's start with `dev`. Don't forget to switch to the `dev` cluster if you deployed on `prod` before with:
```
gcloud container clusters get-credentials <DEV_CLUSTER_NAME> --region <DEV_CLUSTER_REGION>
```

#### Dev environment

The first step is to create a permanent SSD disk that will host the FAISS index. To create a new disk on GCP run:
```
gcloud compute disks create <DISK_NAME>-dev --zone=<ZONE> --type <DISK_TYPE>
```

With:
* `<DISK_NAME>`: the name given to the disk
* `<ZONE>`: the zone where the disk will be located. Preferably the same than where is host your `dev` cluster.
* `<DISK_TYPE>`: the type of the disk needed. You can have an explicit list with the command `gcloud compute disk-types list`.

Once the disk is created, the next step is to rename the `values` YAML files with:
```
mv faissserver/values-dev.examples.yaml faissserver/values-dev.yaml
```

Once done you can fullfil all the variables in it accordingly to the FAISS Server settings you want:
* `bucketPath`: the GCS address of your FAISS index repository.
* `numGpus`: the number of GPUs used by Triton.
* `storage`: the capacity of the `dev` disk.
* `nprobe`: the number of probe you need for your FAISS index. Required only if it is an IVF index.
* `grpcPort`: the gRPC port on which the FAISS server should listen.
* `indexName`: the FAISS index file name.
* `pdName`: the name of the `dev` disk.

Finally, deploy the FAISS Server Helm chart:
```
helm install faissserver ./faissserver -f faissserver/values-dev.yaml
```

#### Prod environment

The exact same logic than for the `dev` must be applied to deploy in the `prod` environment:
```
gcloud container clusters get-credentials <PROD_CLUSTER_NAME> --region <PROD_CLUSTER_REGION>
gcloud compute disks create <DISK_NAME>-prod --zone=<ZONE> --type <DISK_TYPE>
mv faissserver/values-prod.examples.yaml faissserver/values-prod.yaml
helm install faissserver ./faissserver -f faissserver/values-prod.yaml
```

### Deploy Elasticsearch

Each environment (`dev` and `prod`) will contain the same search orchestration service. Let's start with `dev`. Don't forget to switch to the `dev` cluster if you deployed on `prod` before with:
```
gcloud container clusters get-credentials <DEV_CLUSTER_NAME> --region <DEV_CLUSTER_REGION>
```

#### Dev environment

The first step is to create a permanent SSD disk that will host the FAISS index. To create a new disk on GCP run:
```
gcloud compute disks create <DISK_NAME_MASTER>-dev <DISK_NAME_DATA>-dev --zone=<ZONE> --type <DISK_TYPE>
```

Here we create two disks, one for the master node and another one for the data node:
* `<DISK_NAME_MASTER>`: the name given to the disk for the master node.
* `<DISK_NAME_DATA>`: the name given to the disk for the data node.
* `<ZONE>`: the zone where the disk will be located. Preferably the same than where is host your `dev` cluster.
* `<DISK_TYPE>`: the type of the disk needed. You can have an explicit list with the command `gcloud compute disk-types list`.

Once the disk is created, the next step is to rename the `values` YAML files with:
```
mv eck/values-dev.examples.yaml eck/values-dev.yaml
```

Once done you can fullfil all the variables in it accordingly to the Elasticsearch settings you want:
* `storage`: the capacity of the `dev` disk.
* `pdNameMaster`: the name of the `dev` disk for the master node.
* `pdNameData`: the name of the `dev` disk for the data node.

Next, deploy the CRD's and the Elasticsearch operator with:
```
kubectl create -f https://download.elastic.co/downloads/eck/1.8.0/crds.yaml
kubectl apply -f https://download.elastic.co/downloads/eck/1.8.0/operator.yaml
```

Next, set your own Elasticsearch password with:
```
kubectl create secret generic es-cluster-es-elastic-user --from-literal=elastic=<ES_PASSWORD>
```

Finally, deploy the Elasticsearch Helm chart:
```
helm install eck ./eck -f eck/values-dev.yaml
```

#### Prod environment

The exact same logic than for the `dev` must be applied to deploy in the `prod` environment:
```
gcloud container clusters get-credentials <PROD_CLUSTER_NAME> --region <PROD_CLUSTER_REGION>
gcloud compute disks create <DISK_NAME_MASTER>-prod <DISK_NAME_DATA>-prod --zone=<ZONE> --type <DISK_TYPE>
mv eck/values-prod.examples.yaml eck/values-prod.yaml
kubectl create -f https://download.elastic.co/downloads/eck/1.8.0/crds.yaml
kubectl apply -f https://download.elastic.co/downloads/eck/1.8.0/operator.yaml
kubectl create secret generic es-cluster-es-elastic-user --from-literal=elastic=<ES_PASSWORD>
helm install eck ./eck -f eck/values-prod.yaml
```

### Deploy the search orchestration

Each environment (`dev` and `prod`) will contain the same search orchestration service. Let's start with `dev`. Don't forget to switch to the `dev` cluster if you deployed on `prod` before with:
```
gcloud container clusters get-credentials <DEV_CLUSTER_NAME> --region <DEV_CLUSTER_REGION>
```

#### Dev environment

The first step is to create a static IP address that will used by the orchestration service. To create a new static IP address on GCP run:
```
gcloud compute addresses create <IP_NAME>-dev --global --ip-version IPV4
```

With:
* <IP_NAME>: the name you want to give to the address

Once the static IP is created, the next step is to rename the `values` YAML files with:
```
mv searchorchestration/values-dev.examples.yaml searchorchestration/values-dev.yaml
```

Once done you can fullfil all the variables in it accordingly to the search orchestration settings you want:
* `esPort`: the Elasticsearch port
* `esIsSecure`: if Elasticsearch needs a secure connection or not. `false` by default.
* `certName`: the name of the HTTPS certificate that will be created.
* `ipName`: the name of the static IP address to use.
* `domain`: the domain on which the certificate will be associated.

The next step is to create the needed secrets by running the command:
```
kubectl create secret generic credssearchorchestration --from-literal=login=<ES_LOGIN> --from-literal=password=<ES_PASSWORD> --from-literal=secret=<JWT_SECRET>
```

With:
* `<ES_LOGIN>`: the Elasticsearch login that you have set.
* `<ES_PASSWORD>`: the Elasticsearch password that you have set.
* `<JWT_SECRET>`: the JWT secret used to decrypt the received payloads.

Finally, deploy the search orchestration service Helm chart:
```
helm install searchorchestration ./searchorchestration -f searchorchestration/values-dev.yaml
```

#### Prod environment

The exact same logic than for the `dev` must be applied to deploy in the `prod` environment:
```
gcloud container clusters get-credentials <PROD_CLUSTER_NAME> --region <PROD_CLUSTER_REGION>
gcloud compute addresses create <IP_NAME>-prod --global --ip-version IPV4
mv searchorchestration/values-prod.examples.yaml searchorchestration/values-prod.yaml
kubectl create secret generic credssearchorchestration --from-literal=login=<ES_LOGIN> --from-literal=password=<ES_PASSWORD> --from-literal=secret=<JWT_SECRET>
helm install searchorchestration ./searchorchestration -f searchorchestration/values-prod.yaml
```

The entire creation process takes between 30 and 45 minutes to be done.

## Upgrade the cluster and the services

In case something has to be updated in one of the infrastructure, just update the Terraform files and to deploy these updates, just run once again the `apply` command. For updating a service, this is very similar, just update the values in the concerned manifests and run `helm upgrade <SERVICE_NAME> <FOLDER_PATH> -f <VALUES_FILE>`. For both commands, be sure to have the proper environemment selected before to run them.

## Delete the cluster and services

In order to properly delete a cluster and its services, run these commands in the exact same order:
```
helm uninstall searchorchestration
terraform destroy -var-file=<ENV>.tfvars
```

Once again, be sure to have the proper environemment selected before to run them. Once done, only the disks (that contain the FAISS index and the Elasticsearch index) and the IP adresses still remains. It is not advised to delete those unless you really want to destroy everything, otherwise it is better to keep them to have a faster redeployment (no need to recreate the Elasticsearch index and redownload the FAISS index).