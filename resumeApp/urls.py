from django.urls import path
from . import views
from . import payments

urlpatterns = [
    path('analyze/', views.AnalyzeView.as_view(), name='analyze'),
    path('history/', views.AnalysisHistoryView.as_view(), name='history'),
    path('history/<int:id>/', views.AnalysisDetailView.as_view(), name='analysis-detail'),
    path('history/<int:id>/download/', views.DownloadRewrittenCVView.as_view(), name='download-cv'),
    path('history/<int:id>/download-cover-letter/', views.DownloadCoverLetterView.as_view(), name='download-cover-letter'),
    path('payments/initialize/', payments.InitializePaymentView.as_view(), name='payment-initialize'),
    path('payments/verify/', payments.VerifyPaymentView.as_view(), name='payment-verify'),
    path('payments/plans/', payments.PlanListView.as_view(), name='payment-plans'),
    path('payments/webhook/', payments.PaystackWebhookView.as_view(), name='payment-webhook'),
]