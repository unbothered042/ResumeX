from rest_framework import serializers
from .models import Analysis


class AnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = [
            'id',
            'cv_text',
            'job_description',
            'match_score',
            'matched_skills',
            'missing_skills',
            'improvement_tips',
            'summary',
            'cv_rewrite_requested',
            'rewritten_cv',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'match_score',
            'matched_skills',
            'missing_skills',
            'improvement_tips',
            'summary',
            'rewritten_cv',
            'created_at',
        ]