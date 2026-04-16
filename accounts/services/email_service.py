import random

import boto3
from django.conf import settings


class EmailSendError(Exception):
    pass


def generate_verification_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def _get_ses_client():
    return boto3.client(
        "ses",
        region_name=settings.AWS_SES_REGION or settings.AWS_DEFAULT_REGION or None,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
    )


def _send_email(*, email: str, subject: str, body: str) -> None:
    sender = settings.AWS_SES_SENDER_EMAIL
    if not sender:
        raise EmailSendError("SES 발신 이메일이 설정되지 않았습니다.")

    client = _get_ses_client()

    try:
        client.send_email(
            Source=sender,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {
                    "Data": subject,
                    "Charset": "UTF-8",
                },
                "Body": {
                    "Text": {
                        "Data": body,
                        "Charset": "UTF-8",
                    }
                },
            },
        )
    except Exception as exc:
        raise EmailSendError(f"이메일 발송 실패: {str(exc)}") from exc


def send_verification_email(email: str, code: str) -> None:
    _send_email(
        email=email,
        subject="[VeriMarka] 이메일 인증번호 안내",
        body=f"[VeriMarka] 이메일 인증번호는 {code} 입니다. 3분 안에 입력해주세요.",
    )


def send_review_vote_result_email(
    *,
    email: str,
    file_name: str,
    status_name: str,
    upvotes: int,
    downvotes: int,
    end_time_display: str | None,
) -> None:
    decision_label = "승인" if status_name == "Approved" else "거절"
    deadline_label = end_time_display or "-"
    subject = f"[VeriMarka] 커뮤니티 검증 투표가 {decision_label}으로 종료되었습니다"
    body = (
        "[VeriMarka] 커뮤니티 검증 투표 결과를 안내드립니다.\n\n"
        f"- 파일명: {file_name}\n"
        f"- 최종 결과: {decision_label}\n"
        f"- 찬성: {upvotes}\n"
        f"- 반대: {downvotes}\n"
        f"- 종료 시각: {deadline_label}\n\n"
        "분석 기록에서 상세 결과를 확인할 수 있습니다."
    )
    _send_email(email=email, subject=subject, body=body)
