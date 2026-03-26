variable "project_id" {
  description = "Google Cloud Project ID"
  type        = string
}

variable "location" {
  description = "KMS location (e.g., us-central1)"
  type        = string
}

variable "key_ring_name" {
  description = "KMS key ring name"
  type        = string
  default     = "etherion-storage"
}

variable "crypto_key_name" {
  description = "KMS crypto key name"
  type        = string
  default     = "assets-key"
}
