from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User


class MeSerializer(serializers.ModelSerializer):
    providers = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "phone",
            "phone_verified",
            "providers",
        )

    def get_providers(self, obj):
        return [item.provider for item in obj.social_accounts.all()]


class MeUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("username",)


class PhoneSendSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)


class PhoneVerifySerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=6)


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("email", "username", "password")

    def validate_email(self, value):
        email = (value or "").strip().lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("이미 사용 중인 이메일입니다.")
        return email

    def create(self, validated_data):
        return User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
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
