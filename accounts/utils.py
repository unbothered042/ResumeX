import os
import random
import requests
from datetime import timedelta
from django.utils import timezone


def generate_otp_code():
    return f"{random.randint(0, 999999):06d}"


def create_otp(user, purpose, validity_minutes=10):
    from .models import EmailOTP
    # Invalidate any earlier unused codes for this purpose so only the
    # latest one can be redeemed.
    EmailOTP.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)
    return EmailOTP.objects.create(
        user=user,
        code=generate_otp_code(),
        purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=validity_minutes),
    )


def send_otp_email(user, code, purpose):
    from .models import EmailOTP

    subject_map = {
        EmailOTP.PURPOSE_SIGNUP: 'Verify your CVX account',
        EmailOTP.PURPOSE_RESET: 'Reset your CVX password',
    }
    text_map = {
        EmailOTP.PURPOSE_SIGNUP: (
            f"Hi {user.first_name},\n\n"
            f"Your CVX verification code is: {code}\n\n"
            f"This code expires in 10 minutes."
        ),
        EmailOTP.PURPOSE_RESET: (
            f"Hi {user.first_name},\n\n"
            f"Your CVX password reset code is: {code}\n\n"
            f"This code expires in 10 minutes. If you didn't request this, "
            f"you can safely ignore this email."
        ),
    }

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {os.environ.get('RESEND_API_KEY')}",
            "Content-Type": "application/json",
        },
        json={
            "from": os.environ.get('RESEND_FROM_EMAIL', 'CVX <noreply@cvxanalyzer.com.ng>'),
            "to": [user.email],
            "subject": subject_map[purpose],
            "text": text_map[purpose],
        },
        timeout=10,
    )
    return response.status_code, response.text