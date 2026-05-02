from django.urls import path

from .api.views import AIJobDetailView, GuardAnalyzeView


urlpatterns = [
    path("guard/", GuardAnalyzeView.as_view(), name="analysis_guard"),
    path("jobs/<uuid:public_id>/", AIJobDetailView.as_view(), name="analysis_job_detail"),
]
