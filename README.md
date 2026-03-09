# WATSON-BACKEND

주소: http://127.0.0.1:8000/
```
docker compose up -d
docker compose ps
DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py runserver
```

가상환경 세팅
```bash
python -m venv .venv
source .venv/bin/activate
pip install django-environ
pip install -r requirements.txt
```

마이그레이션
```
DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py makemigrations
DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py migrate
```

실행
```
DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py runserver
```

슈퍼유저생성
```
DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py createsuperuser
```

의존성
```
pip freeze > requirements.txt
```

