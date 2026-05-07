# Verimarka Backend Setup

이 문서는 백엔드 로컬 실행 방법을 정리합니다. 기존 상세 인수인계 내용은 [HANDOFF.md](../HANDOFF.md)를 참고하세요.

## 실행 주소

- Backend: `http://127.0.0.1:8000/`
- User Frontend: `http://127.0.0.1:5173/`
- Admin Frontend: `http://127.0.0.1:4173/`

## 1. 의존성 설치

```bash
cd /Users/emfpdlzj/Desktop/verimarka/verimarka-BACKEND
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

개발 도구까지 설치하려면 다음 명령을 추가로 실행합니다.

```bash
pip install -r requirements-dev.txt
pre-commit install
```

## 2. DB / Redis 실행

```bash
docker compose up -d
docker compose ps
```

- PostgreSQL: `127.0.0.1:5433`
- Redis: `127.0.0.1:6379`

## 3. 마이그레이션

```bash
DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py migrate
```

## 4. Django 서버 실행

```bash
DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py runserver 127.0.0.1:8000
```

Redis/Celery 없이 API 서버 기동만 확인할 때는 fake 모드를 사용할 수 있습니다.

```bash
USE_FAKE_REDIS=1 USE_FAKE_CELERY=1 DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py runserver 127.0.0.1:8000
```

## 5. Celery Worker

AI 분석, 저작물 검증, 워터마크 삽입 등 비동기 작업까지 확인하려면 별도 터미널에서 Celery worker를 실행합니다.

```bash
cd /Users/emfpdlzj/Desktop/verimarka/verimarka-BACKEND
source .venv/bin/activate
DJANGO_SETTINGS_MODULE=config.settings.dev celery -A config worker -l info -Q ai,default
```

## 6. 관리자 계정 생성

```bash
DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py createsuperuser
```

