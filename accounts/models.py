from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    def email_validator(self, email):
        try:
            validate_email(email)
        except ValidationError:
            raise ValueError(_("Please enter a valid email address."))

    def create_user(self, first_name, last_name, email, password, **extra_fields):
        if email:
            email = self.normalize_email(email)
            self.email_validator(email)
        else:
            raise ValueError(_("An email address is required."))

        if not first_name:
            raise ValueError(_("First name is required."))

        if not last_name:
            raise ValueError(_("Last name is required."))

        user = self.model(email=email, first_name=first_name, last_name=last_name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('first_name', 'Admin')
        extra_fields.setdefault('last_name', 'User')
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_staff', True)
        return self.create_user(
            first_name=extra_fields.pop('first_name'),
            last_name=extra_fields.pop('last_name'),
            email=email,
            password=password,
            **extra_fields
        )


# Plan tiers, ordered so higher numbers unlock everything lower tiers unlock.
PLAN_NONE = 0
PLAN_STARTER = 1
PLAN_PLUS = 2
PLAN_MAX = 3

PLAN_TIER_CHOICES = [
    (PLAN_NONE, 'None'),
    (PLAN_STARTER, 'Starter'),
    (PLAN_PLUS, 'Plus'),
    (PLAN_MAX, 'Max'),
]

# Single source of truth for pricing/credits — imported by the payment views
# so the amount charged and the credits granted can never drift apart.
PLANS = {
    'starter': {'tier': PLAN_STARTER, 'label': 'Starter', 'price_ngn': 1000, 'credits': 15},
    'plus': {'tier': PLAN_PLUS, 'label': 'Plus', 'price_ngn': 1500, 'credits': 25},
    'max': {'tier': PLAN_MAX, 'label': 'Max', 'price_ngn': 2000, 'credits': 35},
}

# Which plan tier is required to unlock each rewrite/cover-letter level.
# Starter -> Entry only. Plus -> Entry + Mid. Max -> everything.
LEVEL_MIN_TIER = {
    'entry': PLAN_STARTER,
    'mid': PLAN_PLUS,
    'senior': PLAN_MAX,
    'executive': PLAN_MAX,
}

FREE_ANALYSES_LIMIT = 2


class User(AbstractBaseUser):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(max_length=50, unique=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    is_superuser = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- Plans / credits ---
    analysis_credits = models.PositiveIntegerField(default=0)
    free_analyses_used = models.PositiveIntegerField(default=0)
    # Highest plan tier ever purchased. Kept even after credits run out, so a
    # Max buyer who later tops up with Starter doesn't lose Executive access.
    plan_tier = models.PositiveSmallIntegerField(choices=PLAN_TIER_CHOICES, default=PLAN_NONE)

    objects = UserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser

    @property
    def free_analyses_remaining(self):
        return max(0, FREE_ANALYSES_LIMIT - self.free_analyses_used)

    def unlocked_levels(self):
        """Rewrite/cover-letter levels this user's plan_tier currently unlocks."""
        return [level for level, min_tier in LEVEL_MIN_TIER.items() if self.plan_tier >= min_tier]


class Purchase(models.Model):
    """One record per successful top-up. This is the admin dashboard's
    source of truth for revenue and per-user purchase history."""
    STATUS_PENDING = 'pending'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_ADMIN_GRANTED = 'admin_granted'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_ADMIN_GRANTED, 'Admin Granted'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='purchases')
    plan = models.CharField(max_length=20)  # 'starter' / 'plus' / 'max'
    amount_ngn = models.PositiveIntegerField()
    credits_granted = models.PositiveIntegerField()
    paystack_reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_PENDING)
    granted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='plans_granted'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.email} - {self.plan} - {self.status}"