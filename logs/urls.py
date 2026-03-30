from django.urls import path

from .views import AnalysisHistoryView


urlpatterns = [
    path("history/", AnalysisHistoryView.as_view(), name="analysis_history"),
]
