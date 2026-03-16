from django.urls import path

from .views import GuardAnalyzeView


urlpatterns = [
    path("guard/", GuardAnalyzeView.as_view(), name="analysis_guard"),
]
