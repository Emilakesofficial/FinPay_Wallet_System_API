from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    """Serializer for user details"""
    
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'date_joined',
            'is_active'
        ]
        read_only_fields = ['id', 'date_joined', 'last_login']
        
class RegisterSerializer(serializers.ModelSerializer):
    """Serializer for user registration"""
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    
    class Meta:
        model = User
        fields = [
            'username',
            'email',
            'password',
            'password_confirm',
            'first_name',
            'last_name'
        ]
        
    def validate_email(self, value):
        """Validate email is unique."""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered")
        return value.lower()
    
    def validate_username(self, value):
        """Validate username is unique."""
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken")
        return value
    
    def validate(self, data):
        """Validate passwords match and meet requirements."""
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({
                'password_confirm': "Passwords do not match"
            })
        
        # Validate password strength
        try:
            validate_password(data['password'])
        except ValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})
        
        return data
    
    def create(self, validated_data):
        """Create user with hashed password."""
        validated_data.pop('password_confirm')
        
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        
        return user
    
class RegisterResponseSerializer(serializers.Serializer):
    """Serializer for registration response."""
    user = UserSerializer()
    # wallet = serializers.DictField()
    # tokens = serializers.DictField()
    message = serializers.CharField()

    
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = 'email'

    def validate(self, attrs):
        # Let parent authenticate first
        data = super().validate(attrs)

        # Add extra response data
        data['user'] = {
            "id": self.user.id,
            "email": self.user.email,
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
        }

        return data


class TokenRefreshResponseSerializer(serializers.Serializer):
    """Serializer for token refresh response."""
    access = serializers.CharField()
    refresh = serializers.CharField()
        
    
class LoginSerializer(serializers.Serializer):
    """Serializer for user login"""
    
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=True,
        style={'input_type': 'password'}
    )
    
    def validate(self, data):
        """Validate credentials."""
        email = data.get('email')
        password = data.get('password')
        
        if email and password:
            # Try to get user by email
            try:
                user_obj = User.objects.get(email=email)
                username = user_obj.email
            except User.DoesNotExist:
                raise serializers.ValidationError("Invalid credentials")
            
            # Authenticate
            user = authenticate(
                username=username,
                password=password
            )
            
            if not user:
                raise serializers.ValidationError("Invalid credentials")
            
            if not user.is_active:
                raise serializers.ValidationError("Account is disabled")
            
            data['user'] = user
        else:
            raise serializers.ValidationError("Must include email and password")
            
        return data
    
class LogoutSerializer(serializers.Serializer):
    """Serializer for logout (token blacklisting)."""
    refresh = serializers.CharField(required=True)
    
    def validate(self, attrs):
        """Validate refresh token."""
        self.token = attrs['refresh']
        return attrs
    
    def save(self, **kwargs):
        """Blacklist the refresh token."""
        try:
            RefreshToken(self.token).blacklist()
        except Exception as e:
            raise serializers.ValidationError({'detail': 'Invalid token'})

class LogoutResponseSerializer(serializers.Serializer):
    """Serializer for logout response."""
    message = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change."""
    
    old_password = serializers.CharField(
        required=True,
        style={'input_type': 'password'}
    )
    new_password = serializers.CharField(
        required=True,
        style={'input_type': 'password'}
    )
    new_password_confirm = serializers.CharField(
        required=True,
        style={'input_type': 'password'}
    )
    
    def validate_old_password(self, value):
        """Validate old password is correct."""
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Incorrect password")
        return value
    
    def validate(self, data):
        """Validate new passwords match and meet requirements."""
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({
                'new_password_confirm': "Passwords do not match"
            })
        
        # Validate password strength
        try:
            validate_password(data['new_password'])
        except ValidationError as e:
            raise serializers.ValidationError({'new_password': list(e.messages)})
        
        return data
    
class ChangePasswordResponseSerializer(serializers.Serializer):
    """Serializer for change password response."""
    message = serializers.CharField()
    
class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile."""
    
    class Meta:
        model = User
        fields = ['username']
    
    def validate_username(self, value):
        """Validate username is unique (if changed)."""
        user = self.context['request'].user
        if value != user.username and User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken")
        return value

class MessageResponseSerializer(serializers.Serializer):
    """Generic message response."""
    message = serializers.CharField()
        
    
    
