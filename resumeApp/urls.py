from django.urls import path
from . import views

urlpatterns = [
    path('analyze/', views.AnalyzeView.as_view(), name='analyze'),
    path('history/', views.AnalysisHistoryView.as_view(), name='history'),
    path('history/<int:id>/', views.AnalysisDetailView.as_view(), name='analysis-detail'),
    path('history/<int:id>/download/', views.DownloadRewrittenCVView.as_view(), name='download-cv'),
    path('history/<int:id>/download-cover-letter/', views.DownloadCoverLetterView.as_view(), name='download-cover-letter'),
]