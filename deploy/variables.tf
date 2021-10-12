variable "project_id" {
  default     = "expend-on-feature"
  description = "The project ID to host the cluster in"
}

variable "region" {
  default     = "europe-west4"
  description = "The region to host the cluster in"
}

variable "zones" {
  default     = ["europe-west4-c"]
  description = "The zone to host the cluster in (required if is a zonal cluster)"
}

variable "network" {
  default     = "vpc-01"
  description = "The VPC network to host the cluster in"
}

variable "subnetwork" {
  default     = "europe-west4-01"
  description = "The subnetwork to host the cluster in"
}

variable "ip_range_pods_name" {
  default     = "europe-west4-01-gke-01-pods"
  description = "The secondary ip range to use for pods"
}

variable "ip_range_services_name" {
  default     = "europe-west4-01-gke-01-services"
  description = "The secondary ip range to use for services"
}

variable "compute_engine_service_account" {
  default     = "gke-access@expend-on-feature.iam.gserviceaccount.com"
  description = "Service account to associate to the nodes in the cluster"
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
