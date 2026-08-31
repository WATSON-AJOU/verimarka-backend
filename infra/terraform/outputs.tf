output "ec2_instance_id" {
  description = "EC2 instance ID. Set this as the EC2_INSTANCE_ID GitHub secret."
  value       = aws_instance.app.id
}

output "ec2_public_ip" {
  description = "Elastic IP for DNS records and BACKEND_DEPLOY_HOST."
  value       = aws_eip.app.public_ip
}

output "rds_endpoint" {
  description = "PostgreSQL hostname without a port. Use as DB_HOST."
  value       = aws_db_instance.postgresql.address
}

output "rds_port" {
  description = "PostgreSQL port. Use as DB_PORT."
  value       = aws_db_instance.postgresql.port
}

output "database_name" {
  description = "Initial PostgreSQL database name. Use as DB_NAME."
  value       = aws_db_instance.postgresql.db_name
}

output "database_username" {
  description = "PostgreSQL master username. Use as DB_USER."
  value       = aws_db_instance.postgresql.username
  sensitive   = true
}

output "s3_bucket_name" {
  description = "Private upload bucket. Use as AWS_STORAGE_BUCKET_NAME."
  value       = aws_s3_bucket.uploads.id
}

output "aws_region" {
  description = "AWS region. Use as AWS_DEFAULT_REGION and AWS_REGION."
  value       = var.aws_region
}

output "application_environment" {
  description = "Non-secret infrastructure values for the production application environment."
  value = {
    AWS_DEFAULT_REGION      = var.aws_region
    AWS_S3_ENABLED          = true
    AWS_STORAGE_BUCKET_NAME = aws_s3_bucket.uploads.id
    DB_ENGINE               = "django.db.backends.postgresql"
    DB_HOST                 = aws_db_instance.postgresql.address
    DB_NAME                 = aws_db_instance.postgresql.db_name
    DB_PORT                 = tostring(aws_db_instance.postgresql.port)
    REDIS_URL               = "redis://redis:6379/0"
    CELERY_BROKER_URL       = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND   = "redis://redis:6379/0"
  }
}
