from django.contrib import admin
from .models import Analysis


@admin.register(Analysis)
class AnalysisAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'match_score', 'cv_rewrite_requested', 'created_at']
    list_filter = ['cv_rewrite_requested', 'created_at']
    search_fields = ['user__email', 'matched_skills', 'missing_skills']
    readonly_fields = ['cv_text', 'job_description', 'matched_skills', 'missing_skills', 'improvement_tips', 'summary', 'rewritten_cv', 'created_at']
    ordering = ['-created_at']