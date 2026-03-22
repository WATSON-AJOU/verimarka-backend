from django.urls import path
from .views.views import MeView, NicknameAvailabilityView, WithdrawView
from .views.views_oauth import GoogleOAuthLoginView, KakaoOAuthLoginView
from .views.views_sms import PhoneSendCodeView, PhoneVerifyCodeView
from .views.views_email import EmailSendCodeView, EmailVerifyCodeView
from .views.views_auth import SignupView, LoginView

urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
    path("withdraw/", WithdrawView.as_view(), name="withdraw"),
    path("nickname-availability/", NicknameAvailabilityView.as_view(), name="nickname_availability"),
    path("auth/oauth/google/", GoogleOAuthLoginView.as_view(), name="oauth_google"),
    path("auth/oauth/kakao/", KakaoOAuthLoginView.as_view(), name="oauth_kakao"),
    path("phone/send-code/", PhoneSendCodeView.as_view(), name="phone_send_code"),
    path("phone/verify-code/", PhoneVerifyCodeView.as_view(), name="phone_verify_code"),
    path("email/send-code/", EmailSendCodeView.as_view(), name="email_send_code"),
    path("email/verify-code/", EmailVerifyCodeView.as_view(), name="email_verify_code"),
    path("signup/", SignupView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
]
