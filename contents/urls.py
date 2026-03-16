from django.urls import path

from .views import ContentRegisterView


urlpatterns = [
    path("register/", ContentRegisterView.as_view(), name="content_register"),
]
