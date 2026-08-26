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
    matched_skills = models.TextField()
    missing_skills = models.TextField()
    improvement_tips = models.TextField()
    summary = models.TextField()
    cv_rewrite_requested = models.BooleanField(default=False)
    rewritten_cv = models.TextField(null=True, blank=True)
    cover_letter_requested = models.BooleanField(default=False)
    cover_letter = models.TextField(null=True, blank=True)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"