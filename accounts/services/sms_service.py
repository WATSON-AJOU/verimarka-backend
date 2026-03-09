from solapi import SolapiMessageService
from solapi.model import RequestMessage
from django.conf import settings
import random


class SmsSendError(Exception):
    pass


def generate_verification_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def send_verification_sms(phone: str, code: str) -> None:
    message_service = SolapiMessageService(
        api_key=settings.SOLAPI_API_KEY,
        api_secret=settings.SOLAPI_API_SECRET,
    )

    message = RequestMessage(
        from_=settings.SOLAPI_SENDER,
        to=phone,
        text=f"[Verimarka] 인증번호는 {code} 입니다. 3분 안에 입력해주세요.",
    )

    try:
        message_service.send(message)
    except Exception as e:
        raise SmsSendError(f"SMS 발송 실패: {str(e)}")
