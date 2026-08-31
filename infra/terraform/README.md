# Verimarka AWS Terraform

서울 리전(`ap-northeast-2`)에 Verimarka 운영 인프라를 생성합니다. 기존 Docker Compose 배포 방식을 유지하는 최초 도입 범위이며 Terraform state는 이 디렉터리의 로컬 파일로 관리합니다.

## 생성 리소스

- VPC와 인터넷 게이트웨이
- EC2용 public subnet 1개
- RDS용 private subnet 2개(서로 다른 AZ)
- 고정 Elastic IP가 연결된 Amazon Linux 2023 EC2
- private PostgreSQL 16 RDS와 7일 자동 백업
- 암호화, 버전 관리, Public Access Block이 적용된 private S3 bucket
- EC2의 S3 트래픽을 AWS 네트워크 안에서 전달하는 S3 gateway endpoint
- EC2에서 해당 S3 bucket과 SES를 사용할 수 있는 IAM role
- HTTP/HTTPS 공개 및 EC2에서만 PostgreSQL 접근을 허용하는 security group
- SSM Session Manager 접근 권한

Redis는 기존 `docker-compose.prod.yml` 구성대로 EC2 안에서 실행합니다. Route 53 DNS, ACM, Load Balancer, 프론트엔드 빌드, 애플리케이션 secret은 이번 Terraform 범위에 포함하지 않습니다.

## 사전 준비

필요한 도구:

- Terraform 1.10 이상
- AWS CLI
- 리소스를 생성할 권한이 있는 AWS 자격 증명

AWS 자격 증명을 확인합니다.

```bash
aws sts get-caller-identity
```

현재 GitHub Actions는 SSH로 EC2에 배포합니다. 이 방식을 계속 사용하려면 AWS EC2 콘솔 또는 CLI에서 key pair를 먼저 만들고 이름을 `ec2_key_name`에 넣어야 합니다. `ssh_allowed_cidrs`에는 운영자의 고정 IP 또는 고정 egress IP가 있는 CI runner만 허용하는 것을 권장합니다. GitHub-hosted runner의 IP는 고정되지 않으므로 현재 SSH 워크플로와 제한된 CIDR을 안정적으로 함께 사용하려면 self-hosted runner 또는 별도 고정 egress 구성이 필요합니다.

## 최초 적용

이 디렉터리에서 예제 변수 파일을 복사합니다.

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

`terraform.tfvars`에서 최소한 다음 값을 실제 환경에 맞게 변경합니다.

- `db_password`: 16자 이상의 강력한 PostgreSQL 비밀번호
- `ec2_key_name`: 기존 EC2 key pair 이름(SSH 배포를 사용할 때)
- `ssh_allowed_cidrs`: SSH를 허용할 고정 IPv4 CIDR
- `ec2_instance_type`: AI 모델에 필요한 CPU와 메모리

그다음 초기화, 검토, 적용합니다.

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
```

AWS 계정에 실제 비용이 발생하는 작업이므로 `terraform plan`의 생성 대상을 확인한 후 적용합니다. 기본값은 비용을 줄이기 위해 단일 EC2, `db.t4g.micro` RDS, single-AZ RDS를 사용합니다. AI 추론에 기본 `t3.large`가 충분한지는 실제 모델 메모리 사용량으로 확인해야 합니다.

## 애플리케이션 연결

생성 결과를 확인합니다.

```bash
terraform output
terraform output -json application_environment
terraform output -raw database_username
```

EC2의 `/opt/verimarka/verimarka-BACKEND/.env.prod`에 최소한 다음 Terraform 결과를 반영합니다.

```dotenv
DB_ENGINE=django.db.backends.postgresql
DB_HOST=<terraform output rds_endpoint>
DB_PORT=5432
DB_NAME=<terraform output database_name>
DB_USER=<terraform output -raw database_username>
DB_PASSWORD=<terraform.tfvars에 입력한 db_password>

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

AWS_S3_ENABLED=true
AWS_DEFAULT_REGION=ap-northeast-2
AWS_STORAGE_BUCKET_NAME=<terraform output s3_bucket_name>
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```

S3와 SES는 EC2 instance role로 인증되므로 운영 `.env.prod`에 장기 AWS access key를 넣지 않습니다. EC2의 IMDSv2는 필수이며 Docker 컨테이너에서 role credential을 조회할 수 있도록 hop limit 2로 구성되어 있습니다.

애플리케이션 구동에는 위 값 외에도 `config/settings/prod.py`와 `config/settings/base.py`가 요구하는 Django, OAuth, OCR, blockchain 등의 secret이 필요합니다. Terraform은 이 값을 생성하거나 state에 저장하지 않습니다.

## 배포 및 DNS 연결

EC2 user data는 Docker, Git, Docker Compose와 `/opt/verimarka` 디렉터리를 준비합니다. 리포지터리와 AI/blockchain sibling 디렉터리, `.env.prod`, Let's Encrypt 인증서는 민감 정보와 저장소 접근 권한 때문에 자동으로 복사하지 않습니다.

기존 GitHub Actions secrets에는 다음 출력을 반영합니다.

- `AWS_REGION`: `ap-northeast-2`
- `EC2_INSTANCE_ID`: `terraform output -raw ec2_instance_id`
- `BACKEND_DEPLOY_HOST`: `terraform output -raw ec2_public_ip`
- `BACKEND_DEPLOY_USER`: `ec2-user`
- `BACKEND_DEPLOY_PATH`: `/opt/verimarka/verimarka-BACKEND`
- `BACKEND_DEPLOY_SSH_KEY`: `ec2_key_name`에 대응하는 private key

`verimarka.com`, `www.verimarka.com`, `admin.verimarka.com`의 A record를 `ec2_public_ip` 출력값으로 연결한 뒤 `HANDOFF.md`의 Certbot 절차로 인증서를 발급합니다. 현재 Nginx 설정에 예전 EC2 public hostname이 하드코딩되어 있으므로 새 EC2 hostname으로 바꾸거나 해당 hostname 전용 server block을 제거해야 합니다.

## 로컬 state 보안

명시적인 local backend를 사용하며 state는 `infra/terraform/terraform.tfstate`에 저장됩니다. `terraform.tfvars`, state, plan 파일에는 DB 비밀번호 등 민감 값이 포함될 수 있습니다.

- 관련 파일은 `.gitignore`로 Git에서 제외합니다.
- 디스크 암호화와 안전한 별도 백업을 사용합니다.
- state와 plan 파일을 메신저, 이슈, PR에 첨부하지 않습니다.
- 여러 명이 동시에 `apply`하지 않습니다. local backend 잠금은 한 컴퓨터 안에서만 보호합니다.

팀 공동 운영이 시작되면 S3 backend의 암호화와 state locking으로 이전하는 것을 권장합니다.

## 변경 및 삭제

변경 전에는 항상 저장된 state를 사용해 plan을 확인합니다.

```bash
terraform plan
terraform apply
```

RDS와 S3는 데이터 보호를 우선합니다. 기본 설정에서는 RDS deletion protection이 켜져 있고 S3 bucket이 비어 있지 않으면 삭제되지 않습니다. 전체 삭제가 정말 필요한 경우 먼저 데이터를 백업하고 다음 순서로 진행합니다.

1. `db_deletion_protection = false`로 변경하고 `terraform apply`
2. S3 object와 모든 object version을 별도로 삭제
3. 같은 이름의 이전 final RDS snapshot이 없는지 확인
4. `terraform destroy`

RDS 삭제 시 `${project_name}-${environment}-postgresql-final` 이름으로 최종 snapshot을 생성합니다.
