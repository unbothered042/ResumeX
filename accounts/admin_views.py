import uuid
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum
from django.db.models.functions import TruncDate
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAdminUser
from .models import User, Purchase, PLANS
from resumeApp.models import Analysis


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


class AdminRevenueView(APIView):
    """Revenue totals (daily/weekly/monthly/yearly) plus a 30-day daily
    trend for the chart, and total CVs analyzed to date. Revenue only
    counts successful paid purchases — admin-granted plans have
    amount_ngn=0 so they don't inflate revenue."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())
        month_start = today_start.replace(day=1)
        year_start = today_start.replace(month=1, day=1)

        successful = Purchase.objects.filter(status=Purchase.STATUS_SUCCESS)

        def total_since(start):
            return successful.filter(created_at__gte=start).aggregate(total=Sum('amount_ngn'))['total'] or 0

        daily = total_since(today_start)
        weekly = total_since(week_start)
        monthly = total_since(month_start)
        yearly = total_since(year_start)

        # Last 30 days, one point per day, for the trend chart.
        trend_start = today_start - timedelta(days=29)
        trend_qs = (
            successful.filter(created_at__gte=trend_start)
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(total=Sum('amount_ngn'))
            .order_by('day')
        )
        trend_by_day = {row['day'].isoformat(): row['total'] for row in trend_qs}

        trend = []
        for i in range(30):
            day = (trend_start + timedelta(days=i)).date()
            key = day.isoformat()
            trend.append({'date': key, 'revenue': trend_by_day.get(key, 0)})

        total_cvs_analyzed = Analysis.objects.count()

        return Response({
            'daily': daily,
            'weekly': weekly,
            'monthly': monthly,
            'yearly': yearly,
            'trend': trend,
            'total_cvs_analyzed': total_cvs_analyzed,
        }, status=status.HTTP_200_OK)