import random

import boto3
from django.conf import settings


class EmailSendError(Exception):
    pass


def generate_verification_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def send_verification_email(email: str, code: str) -> None:
    sender = settings.AWS_SES_SENDER_EMAIL
    if not sender:
        raise EmailSendError("SES 발신 이메일이 설정되지 않았습니다.")

    client = boto3.client(
        "ses",
        region_name=settings.AWS_SES_REGION or settings.AWS_DEFAULT_REGION or None,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )

    try:
        client.send_email(
            Source=sender,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {
                    "Data": "[VeriMarka] 이메일 인증번호 안내",
                    "Charset": "UTF-8",
                },
                "Body": {
                    "Text": {
                        "Data": f"[VeriMarka] 이메일 인증번호는 {code} 입니다. 3분 안에 입력해주세요.",
                        "Charset": "UTF-8",
                    }
                },
            },
        )
    except Exception as exc:
        raise EmailSendError(f"이메일 발송 실패: {str(exc)}") from exc
