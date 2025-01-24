# serializers.py
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import serializers
from .models import CustomUser
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['user_id', 'username', 'email', 'phone_number', 'role']

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




