import os
import hmac
import hashlib
import requests
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from accounts.models import PLANS, Purchase, User


class PlanListView(APIView):
    """Public pricing info — the frontend renders plan cards straight from
    this instead of hardcoding prices, so the two can never drift apart."""
    permission_classes = [AllowAny]

    def get(self, request):
        plans = [
            {'key': key, 'label': p['label'], 'price_ngn': p['price_ngn'], 'credits': p['credits']}
            for key, p in PLANS.items()
        ]
        return Response(plans, status=status.HTTP_200_OK)


class InitializePaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        plan_key = request.data.get('plan')
        if plan_key not in PLANS:
            return Response({'error': 'Invalid plan. Choose starter, plus, or max.'}, status=status.HTTP_400_BAD_REQUEST)

        plan = PLANS[plan_key]
        user = request.user
        paystack_secret = os.getenv('PAYSTACK_SECRET_KEY')

        headers = {
            'Authorization': f'Bearer {paystack_secret}',
            'Content-Type': 'application/json',
        }
        data = {
            'email': user.email,
            'amount': plan['price_ngn'] * 100,  # Paystack expects kobo
            'currency': 'NGN',
            'callback_url': f'{os.getenv("FRONTEND_URL", "https://cvx-app.vercel.app")}/dashboard?payment=success',
            'metadata': {
                'user_id': user.id,
                'plan': plan_key,
                'app': 'cvx',
            },
        }
        response = requests.post('https://api.paystack.co/transaction/initialize', json=data, headers=headers)
        result = response.json()

        if not result.get('status'):
            return Response({'error': 'Payment initialization failed.'}, status=status.HTTP_400_BAD_REQUEST)

        # Record a pending purchase now so VerifyPaymentView has something
        # to update, and so abandoned checkouts are still visible in the
        # admin dashboard rather than vanishing entirely.
        Purchase.objects.create(
            user=user,
            plan=plan_key,
            amount_ngn=plan['price_ngn'],
            credits_granted=plan['credits'],
            paystack_reference=result['data']['reference'],
            status=Purchase.STATUS_PENDING,
        )

        return Response({
            'authorization_url': result['data']['authorization_url'],
            'reference': result['data']['reference'],
        }, status=status.HTTP_200_OK)


class VerifyPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        reference = request.data.get('reference')
        if not reference:
            return Response({'error': 'Reference is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            purchase = Purchase.objects.get(paystack_reference=reference, user=request.user)
        except Purchase.DoesNotExist:
            return Response({'error': 'Purchase record not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Already verified — return success without double-crediting the user.
        if purchase.status == Purchase.STATUS_SUCCESS:
            return Response({
                'message': 'Payment already verified.',
                'analysis_credits': request.user.analysis_credits,
                'plan_tier': request.user.plan_tier,
            }, status=status.HTTP_200_OK)

        paystack_secret = os.getenv('PAYSTACK_SECRET_KEY')
        headers = {'Authorization': f'Bearer {paystack_secret}'}
        response = requests.get(f'https://api.paystack.co/transaction/verify/{reference}', headers=headers)
        result = response.json()

        if result.get('status') and result['data']['status'] == 'success':
            plan = PLANS[purchase.plan]
            user = request.user
            user.analysis_credits += plan['credits']
            user.plan_tier = max(user.plan_tier, plan['tier'])
            user.save(update_fields=['analysis_credits', 'plan_tier'])

            purchase.status = Purchase.STATUS_SUCCESS
            purchase.verified_at = timezone.now()
            purchase.save(update_fields=['status', 'verified_at'])

            return Response({
                'message': f'Payment verified. {plan["credits"]} credits added.',
                'analysis_credits': user.analysis_credits,
                'plan_tier': user.plan_tier,
            }, status=status.HTTP_200_OK)

        purchase.status = Purchase.STATUS_FAILED
        purchase.save(update_fields=['status'])
        return Response({'error': 'Payment verification failed.'}, status=status.HTTP_400_BAD_REQUEST)


class PaystackWebhookView(APIView):
    """Safety net for InitializePaymentView/VerifyPaymentView: if a user
    pays but closes the tab before the frontend calls /payments/verify/,
    Paystack still hits this endpoint directly and credits get granted
    anyway. Must verify the signature — this endpoint has no auth token,
    so signature checking is the only thing stopping anyone from POSTing
    a fake "payment succeeded" event to grant themselves free credits."""
    permission_classes = [AllowAny]

    def post(self, request):
        paystack_secret = os.getenv('PAYSTACK_SECRET_KEY', '')
        signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')

        expected_signature = hmac.new(
            paystack_secret.encode('utf-8'),
            request.body,
            hashlib.sha512,
        ).hexdigest()

        if not signature or not hmac.compare_digest(signature, expected_signature):
            return Response({'error': 'Invalid signature.'}, status=status.HTTP_400_BAD_REQUEST)

        event = request.data
        if event.get('event') != 'charge.success':
            # Acknowledge and ignore any event type we don't act on.
            return Response(status=status.HTTP_200_OK)

        reference = event.get('data', {}).get('reference')
        if not reference:
            return Response(status=status.HTTP_200_OK)

        purchase = Purchase.objects.filter(paystack_reference=reference).first()
        if not purchase:
            # No matching record — nothing to reconcile. Acknowledge anyway
            # so Paystack doesn't retry indefinitely.
            return Response(status=status.HTTP_200_OK)

        # Idempotent: if /payments/verify/ already handled this, do nothing.
        if purchase.status == Purchase.STATUS_SUCCESS:
            return Response(status=status.HTTP_200_OK)

        plan = PLANS[purchase.plan]
        user = purchase.user
        user.analysis_credits += plan['credits']
        user.plan_tier = max(user.plan_tier, plan['tier'])
        user.save(update_fields=['analysis_credits', 'plan_tier'])

        purchase.status = Purchase.STATUS_SUCCESS
        purchase.verified_at = timezone.now()
        purchase.save(update_fields=['status', 'verified_at'])

        return Response(status=status.HTTP_200_OK)