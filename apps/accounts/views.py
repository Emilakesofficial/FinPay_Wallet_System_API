"""
Views for user authentication and management with JWT.
Properly documented with drf-spectacular for Swagger/OpenAPI.
"""
import logging
from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView as BaseTokenRefreshView
)
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse

from .serializer import (
    UserSerializer,
    RegisterSerializer,
    CustomTokenObtainPairSerializer,
    LogoutSerializer,
    ChangePasswordSerializer,
    ProfileUpdateSerializer,
    RegisterResponseSerializer,
    LogoutResponseSerializer,
    ChangePasswordResponseSerializer,
)
from apps.wallets.selectors import WalletSelectors
from apps.audit.service import AuditService
from common.throttling import AuthRateThrottle

User = get_user_model()
logger = logging.getLogger(__name__)


@extend_schema(
    tags=['Authentication'],
    request=RegisterSerializer,
    responses={
        201: RegisterResponseSerializer,
        400: OpenApiResponse(description='Validation error'),
    },
    description='Register a new user account. Automatically creates a default wallet and returns JWT tokens.',
    summary='Register new user'
)
class RegisterView(APIView):
    """User registration endpoint."""
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthRateThrottle]
    
    @transaction.atomic
    def post(self, request):
        """Register a new user."""
        serializer = RegisterSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create user
        user = serializer.save()
        
        # Create default wallet
        wallet = WalletSelectors.get_or_create_user_wallet(user)
        
        #Audit log
        AuditService.log_user_registered
        
        logger.info(f"New user registered: {user.email}, wallet: {wallet.id}")
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        refresh['email'] = user.email
        refresh['username'] = user.username
        
        return Response(
            {
                'user': UserSerializer(user).data,
                'message': 'Registration successful'
            },
            status=status.HTTP_201_CREATED
        )


@extend_schema(
    tags=['Authentication'],
    request=CustomTokenObtainPairSerializer,
    responses={
        200: CustomTokenObtainPairSerializer,
        400: OpenApiResponse(description='Invalid credentials'),
    },
    description='Login with email and password to receive JWT access and refresh tokens.',
    summary='Login user'
)
class LoginView(TokenObtainPairView):
    """User login endpoint with JWT tokens."""
    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [AuthRateThrottle]
    
    def post(self, request, *args, **kwargs):
        """Login user and return tokens."""
        response = super().post(request, *args, **kwargs)
        
        if response.status_code == status.HTTP_200_OK:
            # Get user and log
            email = request.data.get('email')
            try:
                user = User.objects.get(email=email)
                AuditService.log_user_login(user)
                logger.info(f"User logged in: {email}")
            except User.DoesNotExist:
                pass
        
        return response

@extend_schema(
    tags=['Authentication'],
    description='Refresh access token using refresh token.',
    summary='Refresh access token'
)
class TokenRefreshView(BaseTokenRefreshView):
    """Refresh access token."""
    pass


@extend_schema(
    tags=['Authentication'],
    request=LogoutSerializer,
    responses={
        200: LogoutResponseSerializer,
        400: OpenApiResponse(description='Invalid token'),
    },
    description='Logout by blacklisting the refresh token.',
    summary='Logout user'
)
class LogoutView(APIView):
    """User logout endpoint."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LogoutSerializer  # For Swagger
    
    def post(self, request):
        """Logout user by blacklisting refresh token."""
        serializer = LogoutSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            serializer.save()
            logger.info(f"User logged out: {request.user.email}")
            
            return Response(
                {'message': 'Logout successful'},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Logout failed: {e}")
            return Response(
                {'error': 'Logout failed'},
                status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema_view(
    get=extend_schema(
        tags=['Authentication'],
        responses={200: UserSerializer},
        description='Get current user profile details.',
        summary='Get profile'
    ),
    patch=extend_schema(
        tags=['Authentication'],
        request=ProfileUpdateSerializer,
        responses={200: UserSerializer},
        description='Update current user profile.',
        summary='Update profile'
    ),
    put=extend_schema(
        tags=['Authentication'],
        request=ProfileUpdateSerializer,
        responses={200: UserSerializer},
        description='Update current user profile.',
        summary='Update profile'
    ),
)
class ProfileView(generics.RetrieveUpdateAPIView):
    """Get or update user profile."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        """Return the authenticated user."""
        return self.request.user
    
    def get_serializer_class(self):
        """Return appropriate serializer based on method."""
        if self.request.method in ['PUT', 'PATCH']:
            return ProfileUpdateSerializer
        return UserSerializer


@extend_schema(
    tags=['Authentication'],
    request=ChangePasswordSerializer,
    responses={
        200: ChangePasswordResponseSerializer,
        400: OpenApiResponse(description='Validation error'),
    },
    description='Change password for the authenticated user.',
    summary='Change password'
)
class ChangePasswordView(APIView):
    """Change user password."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChangePasswordSerializer  # For Swagger
    
    def post(self, request):
        """Change password."""
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update password
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        AuditService.log_password_changed(user)
        logger.info(f"Password changed for user: {user.email}")
        
        return Response(
            {'message': 'Password changed successfully'},
            status=status.HTTP_200_OK
        )


@extend_schema(
    tags=['Authentication'],
    responses={200: UserSerializer},
    description='Get details of the currently authenticated user.',
    summary='Get current user'
)
class CurrentUserView(APIView):
    """Get current authenticated user details."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get current user."""
        serializer = UserSerializer(request.user)
        return Response(serializer.data)