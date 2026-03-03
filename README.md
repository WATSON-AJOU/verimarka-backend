# WATSON-BACKEND

주소: http://127.0.0.1:8000/


가상환경 세팅
```bash
python -m venv .venv
source .venv/bin/activate
pip install django djangorestframework django-environ django-cors-headers
pip install djangorestframework-simplejwt
```

실행
```
DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py migrate
DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py runserver
```