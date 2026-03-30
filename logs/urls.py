from django.urls import path

from .views import AnalysisHistoryView, PublicRecentActivityView


urlpatterns = [
    path("history/", AnalysisHistoryView.as_view(), name="analysis_history"),
    path("recent/", PublicRecentActivityView.as_view(), name="public_recent_activity"),
]
