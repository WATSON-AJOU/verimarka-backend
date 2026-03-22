from django.urls import path

from .views import ContentMintView, ContentRegisterView, ContentWatermarkView


urlpatterns = [
    path("register/", ContentRegisterView.as_view(), name="content_register"),
    path("<uuid:public_id>/watermark/", ContentWatermarkView.as_view(), name="content_watermark"),
    path("<uuid:public_id>/mint/", ContentMintView.as_view(), name="content_mint"),
]
