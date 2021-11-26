variable "project_id" {
  description = "The GCP project ID that will host the cluster."
}

variable "prefix" {
  description = "This is the environment where your webapp is deployed. qa, prod, or dev."
}

variable "region" {
  description = "The region that will host the cluster."
}

variable "zones" {
  description = "The zone that will host the cluster (required if you want a zonal cluster). Must be a list."
}

variable "network" {
  description = "The name of the VPC network that will be used by the cluster."
}

variable "subnetwork" {
  description = "The name of the subnetwork used by the VPC."
}

variable "ip_range_pods_name" {
  description = "The name of the secondary ip range to use for the pods."
}

variable "ip_range_services_name" {
  description = "The name of the secondary ip range to use for the services."
}

variable "compute_engine_service_account" {
  description = "The name of the service account to associate to each node in the cluster."
}

variable "triton_machine_type" {
  description = "The GCP machine type for the Triton Server node pool."
}

variable "triton_min_cpu_platform" {
  description = "The targeted min CPU platform for the Triton Server node pool."
}

variable "triton_disk_size_gb" {
  description = "The disk size for the Triton Server node pool."
}

variable "faiss_machine_type" {
  description = "The GCP machine type for the FAISS Server node pool."
}

variable "faiss_min_cpu_platform" {
  description = "The targeted min CPU platform for the FAISS Server node pool."
}

variable "faiss_disk_size_gb" {
  description = "The disk size for the FAISS Server node pool."
}

variable "orchestration_machine_type" {
  description = "The GCP machine type for the Orchestration node pool."
}

variable "orchestration_min_cpu_platform" {
  description = "The targeted min CPU platform for the Orchestration node pool."
}

variable "orchestration_disk_size_gb" {
  description = "The disk size for the Orchestration node pool."
}

variable "elasticsearch_machine_type" {
  description = "The GCP machine type for the Elasticsearch node pool."
}

variable "elasticsearch_min_cpu_platform" {
  description = "The targeted min CPU platform for the Elasticsearch node pool."
}

variable "elasticsearch_disk_size_gb" {
  description = "The disk size for the Elasticsearch node pool."
}

variable "cluster_autoscaling" {
  type = object({
    enabled             = bool
    autoscaling_profile = string
    min_cpu_cores       = number
    max_cpu_cores       = number
    min_memory_gb       = number
    max_memory_gb       = number
    gpu_resources = list(object({
      resource_type = string
      minimum       = number
      maximum       = number
    }))
  })
  default = {
    enabled             = false
    autoscaling_profile = "BALANCED"
    max_cpu_cores       = 0
    min_cpu_cores       = 0
    max_memory_gb       = 0
    min_memory_gb       = 0
    gpu_resources       = []
  }
  description = "Cluster autoscaling configuration. See [more details](https://cloud.google.com/kubernetes-engine/docs/reference/rest/v1beta1/projects.locations.clusters#clusterautoscaling)"
}
