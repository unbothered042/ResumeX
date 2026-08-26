from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .serializers import RegisterSerializer, LoginSerializer
from .models import FREE_ANALYSES_LIMIT
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from resumeApp.models import GuestUsage


def get_client_ip(request):
    """Render sits behind a proxy, so the real client IP is in
    X-Forwarded-For, not REMOTE_ADDR. Kept in sync with the same
    helper in resumeApp/views.py."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class RegisterView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()

            # Carry over any free-trial usage this IP already burned through
            # as a guest, so registering doesn't reset the counter to zero.
            ip = get_client_ip(request)
            guest_usage = GuestUsage.objects.filter(ip_address=ip).first()
            if guest_usage and guest_usage.analyses_used > 0:
                user.free_analyses_used = min(guest_usage.analyses_used, FREE_ANALYSES_LIMIT)
                user.save(update_fields=['free_analyses_used'])

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            user = authenticate(request, email=email, password=password)
            if not user:
                return Response({'error': 'Invalid Credentials'}, status=status.HTTP_401_UNAUTHORIZED)

            token = RefreshToken.for_user(user)
            return Response({
                'message': 'Login successful',
                'user_id': {
                    'id': user.id,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'email': user.email,
                    'is_staff': user.is_staff,
                },
                'refresh': str(token),
                'access': str(token.access_token),
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MeView(APIView):
    """Current user's live credit/plan status — the frontend polls this
    after login, after an analysis, and after a payment to stay in sync."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'is_staff': user.is_staff,
            'analysis_credits': user.analysis_credits,
            'free_analyses_remaining': user.free_analyses_remaining,
            'plan_tier': user.plan_tier,
            'unlocked_levels': user.unlocked_levels(),
        }, status=status.HTTP_200_OK)