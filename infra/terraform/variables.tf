variable "aws_region" {
  description = "AWS region in which to create all resources."
  type        = string
  default     = "ap-northeast-2"
}

variable "project_name" {
  description = "Project name used in resource names and tags."
  type        = string
  default     = "verimarka"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}[a-z0-9]$", var.project_name))
    error_message = "project_name must be 3-22 lowercase letters, numbers, or hyphens and start with a letter."
  }
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "prod"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,10}[a-z0-9]$", var.environment))
    error_message = "environment must be 3-12 lowercase letters, numbers, or hyphens and start with a letter."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.20.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be a valid IPv4 CIDR block."
  }
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public EC2 subnet."
  type        = string
  default     = "10.20.0.0/24"

  validation {
    condition     = can(cidrnetmask(var.public_subnet_cidr))
    error_message = "public_subnet_cidr must be a valid IPv4 CIDR block."
  }
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for the two private RDS subnets."
  type        = list(string)
  default     = ["10.20.10.0/24", "10.20.11.0/24"]

  validation {
    condition     = length(var.private_subnet_cidrs) == 2 && alltrue([for cidr in var.private_subnet_cidrs : can(cidrnetmask(cidr))])
    error_message = "private_subnet_cidrs must contain exactly two valid IPv4 CIDR blocks."
  }
}

variable "ec2_instance_type" {
  description = "EC2 instance type. AI workloads may require a larger instance than the default."
  type        = string
  default     = "t3.large"
}

variable "ec2_ami_id" {
  description = "Optional fixed AMI ID. When null, the latest x86_64 Amazon Linux 2023 AMI is used."
  type        = string
  default     = null
  nullable    = true
}

variable "ec2_key_name" {
  description = "Optional existing EC2 key pair name. Required for the current SSH-based GitHub Actions deployment."
  type        = string
  default     = null
  nullable    = true
}

variable "ssh_allowed_cidrs" {
  description = "IPv4 CIDRs allowed to SSH to EC2. Keep empty when using SSM Session Manager only."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for cidr in var.ssh_allowed_cidrs : can(cidrnetmask(cidr))])
    error_message = "Every ssh_allowed_cidrs value must be a valid IPv4 CIDR block."
  }
}

variable "ec2_root_volume_size" {
  description = "EC2 root EBS volume size in GiB."
  type        = number
  default     = 80

  validation {
    condition     = var.ec2_root_volume_size >= 30
    error_message = "ec2_root_volume_size must be at least 30 GiB."
  }
}

variable "db_name" {
  description = "Initial PostgreSQL database name."
  type        = string
  default     = "verimarka"
}

variable "db_username" {
  description = "PostgreSQL master username."
  type        = string
  default     = "verimarka_admin"
  sensitive   = true
}

variable "db_password" {
  description = "PostgreSQL master password. It is stored in local Terraform state; protect both tfvars and state files."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.db_password) >= 16 && length(var.db_password) <= 128 && !can(regex("[/@\" ]", var.db_password))
    error_message = "db_password must be 16-128 characters and cannot contain spaces, /, @, or double quotes."
  }
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage" {
  description = "Initial RDS gp3 storage in GiB."
  type        = number
  default     = 20
}

variable "db_max_allocated_storage" {
  description = "Maximum RDS storage autoscaling threshold in GiB."
  type        = number
  default     = 100
}

variable "db_multi_az" {
  description = "Whether to enable a Multi-AZ RDS standby. Enabling this increases cost."
  type        = bool
  default     = false
}

variable "db_deletion_protection" {
  description = "Protect the RDS instance from accidental deletion. Disable explicitly before terraform destroy."
  type        = bool
  default     = true
}

variable "s3_bucket_name" {
  description = "Optional globally unique S3 bucket name. When null, AWS adds a unique suffix."
  type        = string
  default     = null
  nullable    = true
}

variable "additional_tags" {
  description = "Additional tags applied to all supported resources."
  type        = map(string)
  default     = {}
}
