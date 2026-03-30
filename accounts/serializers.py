from rest_framework import serializers
from django.contrib.auth import authenticate
from django.utils import timezone
import re
from .models import User


DISPLAY_NAME_PATTERN = r"[A-Za-z0-9가-힣 ]+"
NICKNAME_PATTERN = r"[A-Za-z0-9가-힣 ]+"


def _normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


class MeSerializer(serializers.ModelSerializer):
    providers = serializers.SerializerMethodField()
    last_login_at = serializers.DateTimeField(source="last_login", read_only=True)
    wallet_address = serializers.SerializerMethodField()
    wallet_chain_id = serializers.SerializerMethodField()
    wallet_type = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "nickname",
            "display_name",
            "email",
            "email_verified",
            "phone",
            "phone_verified",
            "last_login_at",
            "auth_provider",
            "is_profile_completed",
            "providers",
            "wallet_address",
            "wallet_chain_id",
            "wallet_type",
        )

    def get_providers(self, obj):
        return [item.provider for item in obj.social_accounts.all()]

    def get_wallet_address(self, obj):
        wallet_link = getattr(obj, "wallet_link", None)
        return wallet_link.address if wallet_link else None

    def get_wallet_chain_id(self, obj):
        wallet_link = getattr(obj, "wallet_link", None)
        return wallet_link.chain_id if wallet_link else None

    def get_wallet_type(self, obj):
        wallet_link = getattr(obj, "wallet_link", None)
        return wallet_link.wallet_type if wallet_link else ""


class MeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("username", "nickname", "display_name", "email")

    def validate_display_name(self, value):
        display_name = _normalize_text(value)
        if not display_name:
            raise serializers.ValidationError("표시명은 비워둘 수 없습니다.")

        if len(display_name) > 20:
            raise serializers.ValidationError("표시명은 20자 이하로 입력해주세요.")

        if not re.fullmatch(DISPLAY_NAME_PATTERN, display_name):
            raise serializers.ValidationError("표시명에는 특수문자를 포함할 수 없습니다.")

        queryset = User.objects.filter(display_name=display_name).exclude(id=self.instance.id)
        if queryset.exists():
            raise serializers.ValidationError("이미 사용 중인 표시명입니다.")

        return display_name

    def validate_nickname(self, value):
        nickname = _normalize_text(value)
        if not nickname:
            raise serializers.ValidationError("닉네임은 비워둘 수 없습니다.")
        if len(nickname) > 30:
            raise serializers.ValidationError("닉네임은 30자 이하로 입력해주세요.")
        if not re.fullmatch(NICKNAME_PATTERN, nickname):
            raise serializers.ValidationError("닉네임에는 특수문자를 포함할 수 없습니다.")

        queryset = User.objects.filter(nickname=nickname).exclude(id=self.instance.id)
        if queryset.exists():
            raise serializers.ValidationError("이미 사용 중인 닉네임입니다.")

        return nickname

    def validate_email(self, value):
        email = _normalize_text(value).lower()
        if not email:
            raise serializers.ValidationError("이메일은 비워둘 수 없습니다.")

        queryset = User.objects.filter(email=email).exclude(id=self.instance.id)
        if queryset.exists():
            raise serializers.ValidationError("이미 사용 중인 이메일입니다.")

        return email

    def update(self, instance, validated_data):
        next_email = validated_data.get("email")
        email_changed = next_email is not None and next_email != instance.email

        if email_changed:
            instance.email_verified = False
            instance.email_verified_at = None

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        update_fields = list(validated_data.keys())
        if email_changed:
            update_fields.extend(["email_verified", "email_verified_at"])

        instance.save(update_fields=update_fields)
        return instance


class PhoneSendSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)


class PhoneVerifySerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=6)


class EmailSendSerializer(serializers.Serializer):
    email = serializers.EmailField()


class EmailVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)


class SignupSerializer(serializers.ModelSerializer):
    nickname = serializers.CharField(write_only=True, max_length=30)
    password = serializers.CharField(write_only=True, min_length=8)
    terms_agreed = serializers.BooleanField(write_only=True)
    privacy_agreed = serializers.BooleanField(write_only=True)

    class Meta:
        model = User
        fields = ("email", "nickname", "password", "terms_agreed", "privacy_agreed")

    def validate_nickname(self, value):
        nickname = _normalize_text(value)
        if not nickname:
            raise serializers.ValidationError("이름은 비워둘 수 없습니다.")
        if len(nickname) > 30:
            raise serializers.ValidationError("닉네임은 30자 이하로 입력해주세요.")
        if not re.fullmatch(NICKNAME_PATTERN, nickname):
            raise serializers.ValidationError("닉네임에는 특수문자를 포함할 수 없습니다.")
        if User.objects.filter(nickname=nickname).exists() or User.objects.filter(username=nickname).exists():
            raise serializers.ValidationError("이미 사용 중인 닉네임입니다.")
        return nickname

    def validate_email(self, value):
        email = _normalize_text(value).lower()
        if not email:
            raise serializers.ValidationError("이메일은 비워둘 수 없습니다.")
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("이미 사용 중인 이메일입니다.")
        return email

    def validate_password(self, value):
        import re

        password = value or ""
        if not re.search(r"[a-z]", password):
            raise serializers.ValidationError("비밀번호는 소문자를 포함해야 합니다.")
        if not re.search(r"[A-Z]", password):
            raise serializers.ValidationError("비밀번호는 대문자를 포함해야 합니다.")
        if not re.search(r"\d", password):
            raise serializers.ValidationError("비밀번호는 숫자를 포함해야 합니다.")
        if not re.search(r"[^A-Za-z0-9]", password):
            raise serializers.ValidationError("비밀번호는 특수문자를 포함해야 합니다.")
        return password

    def validate(self, attrs):
        if not attrs.get("terms_agreed"):
            raise serializers.ValidationError({"terms_agreed": "이용약관 동의가 필요합니다."})
        if not attrs.get("privacy_agreed"):
            raise serializers.ValidationError({"privacy_agreed": "개인정보 처리방침 동의가 필요합니다."})
        return attrs

    def create(self, validated_data):
        nickname = validated_data["nickname"].strip()
        agreed_at = timezone.now()
        return User.objects.create_user(
            username=nickname,
            nickname=nickname,
            display_name=nickname,
            email=validated_data["email"],
            password=validated_data["password"],
            terms_agreed_at=agreed_at,
            privacy_agreed_at=agreed_at,
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = _normalize_text(attrs.get("email")).lower()
        password = attrs.get("password")

        user = User.objects.filter(email=email).first()
        if not user:
            raise serializers.ValidationError(
                "이메일 또는 비밀번호가 올바르지 않습니다."
            )

        if user.is_deleted or not user.is_active:
            raise serializers.ValidationError(
                "탈퇴한 계정입니다. 고객센터로 문의해주세요."
            )

        auth_user = authenticate(username=user.username, password=password)
        if not auth_user:
            raise serializers.ValidationError(
                "이메일 또는 비밀번호가 올바르지 않습니다."
            )

        attrs["user"] = auth_user
        return attrs


class NicknameAvailabilitySerializer(serializers.Serializer):
    nickname = serializers.CharField(max_length=30)

    def validate_nickname(self, value):
        nickname = _normalize_text(value)
        if not nickname:
            raise serializers.ValidationError("닉네임을 입력해주세요.")
        if not re.fullmatch(NICKNAME_PATTERN, nickname):
            raise serializers.ValidationError("닉네임에는 특수문자를 포함할 수 없습니다.")
        return nickname


class DisplayNameAvailabilitySerializer(serializers.Serializer):
    display_name = serializers.CharField(max_length=20)

    def validate_display_name(self, value):
        display_name = _normalize_text(value)
        if not display_name:
            raise serializers.ValidationError("표시명을 입력해주세요.")
        if not re.fullmatch(DISPLAY_NAME_PATTERN, display_name):
            raise serializers.ValidationError("표시명에는 특수문자를 포함할 수 없습니다.")
        return display_name
