data "google_client_config" "default" {}

provider "kubernetes" {
  host                   = "https://${module.gke.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(module.gke.ca_certificate)
}

module "gcp-network" {
  source       = "terraform-google-modules/network/google"
  project_id   = var.project_id
  network_name = "${var.network}-${var.prefix}"

  subnets = [
    {
      subnet_name           = "${var.subnetwork}-${var.prefix}"
      subnet_ip             = "10.0.0.0/17"
      subnet_region         = var.region
    },
  ]

  secondary_ranges = {
    ("${var.subnetwork}-${var.prefix}") = [
      {
        range_name    = "${var.ip_range_pods_name}-${var.prefix}"
        ip_cidr_range = "192.168.0.0/18"
      },
      {
        range_name    = "${var.ip_range_services_name}-${var.prefix}"
        ip_cidr_range = "192.168.64.0/18"
      },
    ]
  }
}

module "gke" {
  source                            = "terraform-google-modules/kubernetes-engine/google"
  project_id                        = var.project_id
  name                              = "${var.project_id}-${var.prefix}-cluster"
  regional                          = false
  region                            = var.region
  zones                             = var.zones
  network                           = module.gcp-network.network_name
  subnetwork                        = module.gcp-network.subnets_names[0]
  ip_range_pods                     = "${var.ip_range_pods_name}-${var.prefix}"
  ip_range_services                 = "${var.ip_range_services_name}-${var.prefix}"
  create_service_account            = false
  remove_default_node_pool          = true

  node_pools = [
    /*{
      name               = "pool-tritonserver"
      machine_type       = var.triton_machine_type
      min_cpu_platform   = var.triton_min_cpu_platform
      node_locations     = var.zones[0]
      max_count          = 3
      min_count          = 1
      initial_node_count = 1
      disk_type          = "pd-ssd"
      disk_size_gb       = var.triton_disk_size_gb
      service_account    = var.compute_engine_service_account
    },
    {
      name               = "pool-faissserver"
      machine_type       = var.faiss_machine_type
      node_locations     = var.zones[0]
      min_cpu_platform   = var.faiss_min_cpu_platform
      max_count          = 3
      min_count          = 1
      initial_node_count = 1
      disk_type          = "pd-ssd"
      disk_size_gb       = var.faiss_disk_size_gb
      service_account    = var.compute_engine_service_account
    },*/
    {
      name               = "pool-elasticsearch"
      machine_type       = var.elasticsearch_machine_type
      node_locations     = var.zones[0]
      min_cpu_platform   = var.elasticsearch_min_cpu_platform
      max_count          = 3
      min_count          = 1
      initial_node_count = 1
      disk_type          = "pd-ssd"
      disk_size_gb       = var.elasticsearch_disk_size_gb
      service_account    = var.compute_engine_service_account
    },
    {
      name               = "pool-orchestration"
      machine_type       = var.orchestration_machine_type
      node_locations     = var.zones[0]
      min_cpu_platform   = var.orchestration_min_cpu_platform
      max_count          = 3
      min_count          = 1
      initial_node_count = 1
      disk_type          = "pd-ssd"
      disk_size_gb       = var.orchestration_disk_size_gb
      service_account    = var.compute_engine_service_account
    }
  ]
}

module "k8s-gcs-access-workload-identity" {
  source     = "terraform-google-modules/kubernetes-engine/google//modules/workload-identity"
  name       = "iden-k8s-gcs-access-${var.prefix}"
  namespace  = "default"
  project_id = "${var.project_id}"
  roles      = ["roles/storage.admin"]
}
