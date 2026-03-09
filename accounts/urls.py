from django.urls import path
from .views import MeView
from .views_oauth import GoogleOAuthLoginView, KakaoOAuthLoginView
from .views_sms import PhoneSendCodeView, PhoneVerifyCodeView
from .views_auth import SignupView, LoginView

urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
    path("auth/oauth/google/", GoogleOAuthLoginView.as_view(), name="oauth_google"),
    path("auth/oauth/kakao/", KakaoOAuthLoginView.as_view(), name="oauth_kakao"),
    path("phone/send-code/", PhoneSendCodeView.as_view(), name="phone_send_code"),
    path("phone/verify-code/", PhoneVerifyCodeView.as_view(), name="phone_verify_code"),
    path("signup/", SignupView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
]
