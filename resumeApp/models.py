from django.db import models
from accounts.models import User

LEVEL_CHOICES = [
    ('entry', 'Entry Level'),
    ('mid', 'Mid Level'),
    ('senior', 'Senior Level'),
    ('executive', 'Executive'),
]


class GuestUsage(models.Model):
    """Tracks free-trial usage for unauthenticated users by IP address,
    since there's no account to attach a counter to."""
    ip_address = models.GenericIPAddressField(unique=True)
    analyses_used = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ip_address} - {self.analyses_used} used"


class Analysis(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='analyses')
    cv_text = models.TextField()
    job_description = models.TextField()
    match_score = models.IntegerField()
    score_breakdown = models.JSONField(null=True, blank=True)
    matched_skills = models.TextField()
    missing_skills = models.TextField()
    improvement_tips = models.TextField()
    summary = models.TextField()

    cv_rewrite_requested = models.BooleanField(default=False)
    rewritten_cv = models.TextField(null=True, blank=True)
    rewritten_match_score = models.IntegerField(null=True, blank=True)
    rewritten_score_breakdown = models.JSONField(null=True, blank=True)
    rewrite_level = models.CharField(max_length=10, choices=LEVEL_CHOICES, null=True, blank=True)

    cover_letter_requested = models.BooleanField(default=False)
    cover_letter = models.TextField(null=True, blank=True)
    cover_letter_level = models.CharField(max_length=10, choices=LEVEL_CHOICES, null=True, blank=True)

    # Legacy column from when rewrite/cover letter were requested together
    # at analysis time and shared one level. No longer written to by new
    # requests — kept so old rows keep their data. Safe to drop in a later
    # migration once you've confirmed nothing reads it anymore.
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class CVRebuild(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rebuilds')
    original_cv_text = models.TextField()
    rebuilt_cv = models.TextField()
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='mid')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - rebuild - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class CVCreation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cv_creations')
    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    location = models.CharField(max_length=150, blank=True)
    linkedin = models.URLField(blank=True)
    portfolio = models.URLField(blank=True)
    professional_summary = models.TextField(blank=True)
    work_experience = models.JSONField(default=list)
    education = models.JSONField(default=list)
    skills = models.JSONField(default=list)
    projects = models.JSONField(default=list)
    certifications = models.JSONField(default=list)
    achievements = models.JSONField(default=list)
    reference_cv_text = models.TextField(blank=True, null=True)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='mid')
    generated_cv = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - creation - {self.created_at.strftime('%Y-%m-%d %H:%M')}"