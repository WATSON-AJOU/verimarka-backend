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


앱 구조
```
	•	accounts : 회원가입, 로그인, OAuth, SMS 인증, 프로필, 권한
    
	•	contents : 이미지/문서 원본 업로드, 상태 관리, 결과 파일
	•	analysis : AI 판정 요청/응답, 유사도 결과, 후보 이미지, 판정 상태
	•	reviews : REVIEW 상태 케이스, 투표, 투표 결과
	•	tokens : NFT 발행, 토큰 메타데이터, 컨트랙트 연동 결과
	•	wallets : 지갑 연동, 주소 저장, provider 정보

	•	logs : 판정 로그, 액션 로그, 분쟁 대응 로그
	•	common : 공통 base model, enum, validator, util
```
