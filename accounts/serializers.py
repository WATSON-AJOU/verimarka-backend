from rest_framework import serializers
from django.contrib.auth import authenticate
from django.utils import timezone
from .models import User


class MeSerializer(serializers.ModelSerializer):
    providers = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "nickname",
            "display_name",
            "email",
            "phone",
            "phone_verified",
            "auth_provider",
            "is_profile_completed",
            "providers",
        )

    def get_providers(self, obj):
        return [item.provider for item in obj.social_accounts.all()]


class MeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("username", "nickname", "display_name")

    def validate_nickname(self, value):
        nickname = (value or "").strip()
        if not nickname:
            raise serializers.ValidationError("닉네임은 비워둘 수 없습니다.")

        queryset = User.objects.filter(nickname=nickname).exclude(id=self.instance.id)
        if queryset.exists():
            raise serializers.ValidationError("이미 사용 중인 닉네임입니다.")

        return nickname


class PhoneSendSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)


class PhoneVerifySerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=6)


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    terms_agreed = serializers.BooleanField(write_only=True)
    privacy_agreed = serializers.BooleanField(write_only=True)

    class Meta:
        model = User
        fields = ("email", "username", "password", "terms_agreed", "privacy_agreed")

    def validate_username(self, value):
        username = (value or "").strip()
        if not username:
            raise serializers.ValidationError("이름은 비워둘 수 없습니다.")
        return username

    def validate_email(self, value):
        email = (value or "").strip().lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("이미 사용 중인 이메일입니다.")
        return email

    def validate(self, attrs):
        if not attrs.get("terms_agreed"):
            raise serializers.ValidationError({"terms_agreed": "이용약관 동의가 필요합니다."})
        if not attrs.get("privacy_agreed"):
            raise serializers.ValidationError({"privacy_agreed": "개인정보 처리방침 동의가 필요합니다."})
        return attrs

    def create(self, validated_data):
        username = validated_data["username"].strip()
        agreed_at = timezone.now()
        return User.objects.create_user(
            username=username,
            nickname=username,
            display_name=username,
            email=validated_data["email"],
            password=validated_data["password"],
            terms_agreed_at=agreed_at,
            privacy_agreed_at=agreed_at,
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = (attrs.get("email") or "").strip().lower()
        password = attrs.get("password")

        user = User.objects.filter(email=email).first()
        if not user:
            raise serializers.ValidationError(
                "이메일 또는 비밀번호가 올바르지 않습니다."
            )

        auth_user = authenticate(username=user.username, password=password)
        if not auth_user:
            raise serializers.ValidationError(
                "이메일 또는 비밀번호가 올바르지 않습니다."
            )

        attrs["user"] = auth_user
        return attrs
