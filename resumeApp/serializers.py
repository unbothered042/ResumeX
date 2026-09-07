from rest_framework import serializers
from .models import Analysis, CVRebuild, CVCreation


class AnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Analysis
        fields = [
            'id', 'cv_text', 'job_description', 'match_score',
            'matched_skills', 'missing_skills', 'improvement_tips',
            'summary', 'cv_rewrite_requested', 'rewritten_cv',
            'cover_letter_requested', 'cover_letter', 'created_at',
        ]
        read_only_fields = [
            'id', 'match_score', 'matched_skills', 'missing_skills',
            'improvement_tips', 'summary', 'rewritten_cv',
            'cover_letter', 'created_at',
        ]


class CVRebuildSerializer(serializers.ModelSerializer):
    class Meta:
        model = CVRebuild
        fields = [
            'id', 'original_cv_text', 'rebuilt_cv', 'level', 'created_at',
        ]
        read_only_fields = [
            'id', 'rebuilt_cv', 'created_at',
        ]


class CVCreationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CVCreation
        fields = [
            'id', 'full_name', 'email', 'phone', 'location', 'linkedin', 'portfolio',
            'professional_summary', 'work_experience', 'education', 'skills',
            'projects', 'certifications', 'achievements', 'level',
            'generated_cv', 'created_at',
        ]
        read_only_fields = ['id', 'generated_cv', 'created_at']