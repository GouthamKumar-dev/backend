# serializers.py
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import serializers
from .models import CustomUser,UserRole
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['user_id', 'username', 'email', 'phone_number','default_shipping_address', 'role']

# **Signup Serializer**
class SignupSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'phone_number', 'password']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = CustomUser.objects.create_user(**validated_data)
        return user

# **Login Serializer**
class LoginSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    password = serializers.CharField()

class OTPVerifySerializer(serializers.Serializer):
    identifier = serializers.CharField()
    otp = serializers.CharField()

class ResetPasswordSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    otp = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

class CreateUserSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=UserRole.choices, required=True)  # Role is mandatory

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'phone_number', 'password', 'role']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        request_user = self.context['request'].user  # Get the currently logged-in user

        # Ensure only admins & staff can create users, and enforce role restrictions
        if request_user.role == UserRole.ADMIN:
            # Admins can create ADMIN, STAFF, and CUSTOMERS
            allowed_roles = [UserRole.ADMIN, UserRole.STAFF, UserRole.CUSTOMER]
        elif request_user.role == UserRole.STAFF:
            # Staff can only create STAFF and CUSTOMERS
            allowed_roles = [UserRole.STAFF, UserRole.CUSTOMER]
        else:
            raise serializers.ValidationError("You are not authorized to create users.")

        # Check if the provided role is allowed
        if validated_data['role'] not in allowed_roles:
            raise serializers.ValidationError(f"You can only create users with roles: {allowed_roles}")

        # Create user
        user = CustomUser.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            phone_number=validated_data['phone_number'],
            password=validated_data['password'],
            role=validated_data['role'],  # Role is mandatory now
        )
        return user

# custom token
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Add custom claims if needed
        return token

class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        refresh = attrs['refresh']

        try:
            # Decode the refresh token
            token = RefreshToken(refresh)

            # Ensure user_id is used instead of id
            user_id = token.payload.get('user_id')
            if not user_id:
                raise InvalidToken("User ID not found in the token.")

            # Optional: Add more validation if necessary

            # Generate new tokens
            data = {
                'access': str(token.access_token),
            }
            return data

        except Exception as e:
            raise InvalidToken("The token is invalid or expired.") from e
        
class LoginWithEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()        

#customer_signup
class CustomerSignupSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'phone_number']  # No password field

    def create(self, validated_data):
        validated_data['role'] = UserRole.CUSTOMER  # Force role to CUSTOMER
        user = CustomUser.objects.create(**validated_data)
        return user


