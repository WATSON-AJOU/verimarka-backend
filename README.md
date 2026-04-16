# WATSON-BACKEND

로컬 기본 주소: `http://127.0.0.1:8000/`

## 로컬 실행 순서

### 1. 가상환경 / 의존성
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

로컬 개발에서 포맷터와 pre-commit 훅까지 같이 쓰려면:

```bash
pip install -r requirements-dev.txt
pre-commit install
```

### 2. 로컬 DB / Redis 실행
현재 `docker-compose.yml`에는 `db`, `redis`만 있습니다.

```bash
docker compose up -d
docker compose ps
```

- Postgres: `127.0.0.1:5433`
- Redis: `127.0.0.1:6379`

### 3. 마이그레이션
```bash
DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py makemigrations
DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py migrate
```

### 4. Django 서버 실행
```bash
DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py runserver
```

### 5. Celery 워커 실행
AI 작업(등록 분석, 저작물 검증, 워터마크 삽입)은 Celery + Redis 큐로 처리됩니다.
로컬 테스트 시 Django 서버와 별도로 워커를 반드시 띄워야 합니다.

```bash
DJANGO_SETTINGS_MODULE=config.settings.dev celery -A config worker -l info -Q ai,default
```

### 6. 관리자 계정 생성
```bash
DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py createsuperuser
```

## 한 번에 필요한 로컬 프로세스

최소 실행 조합:

1. `docker compose up -d`
2. `DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py runserver`
3. `DJANGO_SETTINGS_MODULE=config.settings.dev celery -A config worker -l info -Q ai,default`

Celery 워커가 없으면 아래 기능은 응답이 `queued`에서 멈춥니다.

- 저작물 등록 분석
- 저작물 검증
- 워터마크 삽입

## 자주 쓰는 확인 명령

### DB / Redis 상태 확인
```bash
docker compose ps
```

### Redis 응답 확인
```bash
redis-cli -p 6379 ping
```

### Celery 워커 큐 확인
```bash
DJANGO_SETTINGS_MODULE=config.settings.dev celery -A config inspect active
DJANGO_SETTINGS_MODULE=config.settings.dev celery -A config inspect reserved
```

## 코드 포맷 / pre-commit

이 저장소는 `ruff check --fix` 와 `ruff format` 을 pre-commit 훅으로 사용합니다.

수동 실행:

```bash
ruff check . --fix
ruff format .
```

전체 파일에 훅 실행:

```bash
pre-commit run --all-files
```

## 로깅

백엔드는 공통 콘솔 로깅과 `X-Request-Id` 기반 요청 추적을 사용합니다.

- 모든 응답에 `X-Request-Id` 헤더가 추가됩니다.
- 로그 포맷에는 시간, 레벨, `request_id`, 로거명, 라인번호가 포함됩니다.
- 로그 레벨은 `DJANGO_LOG_LEVEL` 환경변수로 조절합니다.

예:

```bash
DJANGO_LOG_LEVEL=DEBUG
```

## 운영 compose

운영은 별도 파일을 사용합니다.

```bash
docker compose -f docker-compose.prod.yml up -d
```

## 백엔드 CI/CD

GitHub Actions 워크플로는 `main` 브랜치 push 또는 수동 실행 시 운영 서버에 SSH 접속해서 백엔드 리포지토리를 갱신한 뒤, 아래 명령을 실행합니다.

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

워크플로 파일:
`/.github/workflows/deploy-backend.yml`

필수 GitHub Secrets:
- `BACKEND_DEPLOY_HOST`
- `BACKEND_DEPLOY_PORT`
- `BACKEND_DEPLOY_USER`
- `BACKEND_DEPLOY_SSH_KEY`
- `BACKEND_DEPLOY_PATH`

선택 GitHub Secrets:
- `BACKEND_DEPLOY_BRANCH`
- `BACKEND_HEALTHCHECK_URL`

권장 운영값:
- `BACKEND_DEPLOY_BRANCH`: `main`
- `BACKEND_DEPLOY_PATH`: 운영 서버의 `verimarka-BACKEND` 리포지토리 경로
  예: `/opt/verimarka/verimarka-BACKEND`
- `BACKEND_HEALTHCHECK_URL`: 배포 후 확인할 API 주소
  예: `https://verimarka.com/api/`

주의:
- 운영 서버의 `BACKEND_DEPLOY_PATH` 는 이미 `origin` 이 `WATSON-AJOU/WATSON-BACKEND` 로 연결되어 있어야 합니다.
- 운영 서버에 `docker`, `docker compose`, `git`, `curl` 이 설치되어 있어야 합니다.
- 운영용 `.env.prod` 는 서버에만 두고 GitHub Secrets 로 올리지 않는 전제를 사용합니다.

## 운영 인증서 발급 / 갱신

도메인 구성:

- `verimarka.com` → 사용자용 웹사이트
- `www.verimarka.com` → 사용자용 웹사이트
- `admin.verimarka.com` → 관리자 웹사이트

현재 nginx는 하나의 Let's Encrypt 인증서에 위 3개 도메인이 함께 포함된 SAN 인증서를 사용하도록 되어 있습니다.

최초 발급 또는 `admin.verimarka.com` 추가 발급:

```bash
docker compose -f docker-compose.prod.yml run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d verimarka.com \
  -d www.verimarka.com \
  -d admin.verimarka.com
```

발급 후 nginx 재시작:

```bash
docker compose -f docker-compose.prod.yml restart verimarka-nginx
```

주의:

- `admin.verimarka.com` DNS가 현재 서버를 가리켜야 합니다.
- 80 포트가 외부에서 접근 가능해야 webroot 인증이 통과합니다.

## 앱 구조
```text
accounts   : 회원가입, 로그인, OAuth, SMS 인증, 프로필, 권한
contents   : 이미지 원본 업로드, 상태 관리, 결과 파일
analysis   : AI 판정 요청/응답, 유사도 결과, 후보 이미지, 비동기 작업 큐
reviews    : REVIEW 상태 케이스, 투표, 투표 결과
tokens     : NFT 발행, 토큰 메타데이터, 컨트랙트 연동 결과
wallets    : 지갑 연동, 주소 저장, provider 정보
logs       : 판정 로그, 검증 이력, 분쟁 대응 로그
```

## 참고

- dev 환경에서도 현재 구조상 S3 업로드를 전제로 동작하는 기능이 있습니다.
- `verify`, `register`, `watermark`는 큐 기반이라 Redis + Celery가 빠지면 정상 동작하지 않습니다.
- 의존성 변경 후에는 필요 시 `pip freeze > requirements.txt`로 반영합니다.
