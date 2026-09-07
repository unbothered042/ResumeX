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


class CVRebuild(models.Model):
    """A standalone 'rebuild my CV' request — no job description or match
    scoring involved, just a general professional rewrite of an existing CV."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rebuilds')
    original_cv_text = models.TextField()
    rebuilt_cv = models.TextField()
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='mid')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - rebuild - {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class CVCreation(models.Model):
    """A CV built from scratch via the guided wizard. Work experience,
    education, skills, projects, certifications, and achievements are
    stored as JSON so the frontend can freely add/remove multiple entries
    per section without any backend schema changes."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cv_creations')

    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    location = models.CharField(max_length=150, blank=True)
    linkedin = models.URLField(blank=True)
    portfolio = models.URLField(blank=True)

    # Optional — AI writes one from the rest of the data if left blank.
    professional_summary = models.TextField(blank=True)

    work_experience = models.JSONField(default=list)   # [{title, company, start_date, end_date, location, bullets: [str]}]
    education = models.JSONField(default=list)          # [{degree, institution, start_date, end_date, details}]
    skills = models.JSONField(default=list)             # [{category, items: [str]}]
    projects = models.JSONField(default=list)           # [{name, description}]
    certifications = models.JSONField(default=list)     # [{name, issuer, date}]
    achievements = models.JSONField(default=list)        # [str]

    # Optional existing CV uploaded purely as a style/content reference —
    # never copied verbatim, never treated as a source of new facts.
    reference_cv_text = models.TextField(blank=True, null=True)

    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='mid')
    generated_cv = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - creation - {self.created_at.strftime('%Y-%m-%d %H:%M')}"