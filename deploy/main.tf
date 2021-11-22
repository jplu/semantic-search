data "google_client_config" "default" {}

provider "kubernetes" {
  host                   = "https://${module.gke.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(module.gke.ca_certificate)
}

module "gcp-network" {
  source       = "terraform-google-modules/network/google"
  project_id   = var.project_id
  network_name = var.network

  subnets = [
    {
      subnet_name           = var.subnetwork
      subnet_ip             = "10.0.0.0/17"
      subnet_region         = var.region
    },
  ]

  secondary_ranges = {
    (var.subnetwork) = [
      {
        range_name    = var.ip_range_pods_name
        ip_cidr_range = "192.168.0.0/18"
      },
      {
        range_name    = var.ip_range_services_name
        ip_cidr_range = "192.168.64.0/18"
      },
    ]
  }
}

module "gke" {
  source                            = "terraform-google-modules/kubernetes-engine/google"
  project_id                        = var.project_id
  name                              = "${var.project_id}-cluster"
  regional                          = false
  region                            = var.region
  zones                             = var.zones
  network                           = module.gcp-network.network_name
  subnetwork                        = module.gcp-network.subnets_names[0]
  ip_range_pods                     = var.ip_range_pods_name
  ip_range_services                 = var.ip_range_services_name
  create_service_account            = false
  remove_default_node_pool          = true

  node_pools = [
    {
      name               = "pool-tritonserver"
      machine_type       = "n2-custom-16-8192"
      min_cpu_platform   = "Intel Ice Lake"
      node_locations     = var.zones[0]
      max_count          = 3
      min_count          = 1
      initial_node_count = 1
      disk_type          = "pd-ssd"
      disk_size_gb       = 50
      service_account    = var.compute_engine_service_account
    },
    {
      name               = "pool-faissserver"
      machine_type       = "n2-custom-32-61440"
      node_locations     = var.zones[0]
      min_cpu_platform   = "Intel Ice Lake"
      max_count          = 3
      min_count          = 1
      initial_node_count = 1
      disk_type          = "pd-ssd"
      disk_size_gb       = 20
      service_account    = var.compute_engine_service_account
    },
    {
      name               = "pool-orchestration"
      machine_type       = "n1-highcpu-4"
      node_locations     = var.zones[0]
      max_count          = 3
      min_count          = 1
      initial_node_count = 1
      disk_type          = "pd-ssd"
      disk_size_gb       = 10
      service_account    = var.compute_engine_service_account
    },
    {
      name               = "pool-elasticsearch"
      machine_type       = "n1-highcpu-16"
      //machine_type       = "n1-standard-4"
      node_locations     = var.zones[0]
      max_count          = 3
      min_count          = 1
      initial_node_count = 1
      disk_type          = "pd-ssd"
      disk_size_gb       = 10
      service_account    = var.compute_engine_service_account
    }
  ]
}

module "k8s-gcs-access-workload-identity" {
  source     = "terraform-google-modules/kubernetes-engine/google//modules/workload-identity"
  name       = "iden-k8s-gcs-access"
  namespace  = "default"
  project_id = "expend-on-feature"
  roles      = ["roles/storage.admin"]
}

