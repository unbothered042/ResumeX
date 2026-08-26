import uuid
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAdminUser
from .models import User, Purchase, PLANS


class AdminUserSerializer(serializers.ModelSerializer):
    plan_tier_label = serializers.CharField(source='get_plan_tier_display', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'first_name', 'last_name', 'email', 'phone',
            'is_active', 'created_at',
            'analysis_credits', 'free_analyses_used', 'plan_tier', 'plan_tier_label',
        ]


class AdminUserListView(APIView):
    """Lists every registered user. Staff-only."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        users = User.objects.all().order_by('-created_at')
        serializer = AdminUserSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminGrantPlanView(APIView):
    """Lets an admin manually grant a user credits/plan tier without going
    through Paystack — e.g. for support cases, promos, or comps."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        user_id = request.data.get('user_id')
        plan_key = request.data.get('plan')

        if plan_key not in PLANS:
            return Response({'error': 'Invalid plan. Choose starter, plus, or max.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        plan = PLANS[plan_key]
        target_user.analysis_credits += plan['credits']
        target_user.plan_tier = max(target_user.plan_tier, plan['tier'])
        target_user.save(update_fields=['analysis_credits', 'plan_tier'])

        Purchase.objects.create(
            user=target_user,
            plan=plan_key,
            amount_ngn=0,
            credits_granted=plan['credits'],
            paystack_reference=f"ADMIN-{uuid.uuid4().hex[:16]}",
            status=Purchase.STATUS_ADMIN_GRANTED,
            granted_by=request.user,
            verified_at=timezone.now(),
        )

        return Response({
            'message': f"Granted {plan['label']} plan to {target_user.email}.",
            'user': AdminUserSerializer(target_user).data,
        }, status=status.HTTP_200_OK)