# Outputs for the shared database module

output "instance_name" {
  description = "Name of the Cloud SQL instance"
  value       = google_sql_database_instance.shared_db.name
}

output "connection_name" {
  description = "Connection name of the Cloud SQL instance"
  value       = google_sql_database_instance.shared_db.connection_name
}

output "private_ip_address" {
  description = "Private IP address of the Cloud SQL instance"
  value       = google_sql_database_instance.shared_db.private_ip_address
}

output "public_ip_address" {
  description = "Public IP address of the Cloud SQL instance (if enabled)"
  value       = google_sql_database_instance.shared_db.public_ip_address
}

output "database_name" {
  description = "Name of the main database"
  value       = google_sql_database.main_db.name
}

output "database_user" {
  description = "Database user name"
  value       = google_sql_user.db_user.name
}

output "password_secret_id" {
  description = "Secret Manager secret ID for the database password"
  value       = google_secret_manager_secret.db_password.secret_id
}

output "password_secret_version" {
  description = "Secret Manager secret version for the database password"
  value       = google_secret_manager_secret_version.db_password.version
}