# serializers.py
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework import serializers
from .models import CustomUser,UserRole
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from .models import AdminNotification

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['user_id', 'username', 'email', 'phone_number','default_shipping_address', 'role']

class BankDetailsSerializer(serializers.ModelSerializer):
    """Serializer for admin bank details - sensitive information"""
    class Meta:
        model = CustomUser
        fields = [
            'bank_account_holder_name',
            'bank_account_number',
            'bank_ifsc_code',
            'bank_name',
            'bank_branch',
            'upi_id',
            'pan_number',
            'gstin',
            'bank_details_verified',
            'bank_verified_at'
        ]
        read_only_fields = ['bank_details_verified', 'bank_verified_at']

class AdminProfileSerializer(serializers.ModelSerializer):
    """Extended serializer for admin profile with bank details"""
    class Meta:
        model = CustomUser
        fields = [
            'user_id', 
            'username', 
            'email', 
            'phone_number',
            'default_shipping_address', 
            'role',
            'bank_account_holder_name',
            'bank_account_number',
            'bank_ifsc_code',
            'bank_name',
            'bank_branch',
            'upi_id',
            'pan_number',
            'gstin',
            'bank_details_verified',
            'bank_verified_at',
            'created_at'
        ]
        read_only_fields = ['bank_details_verified', 'bank_verified_at']

# **Login Serializer**
class LoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField()

class OTPVerifySerializer(serializers.Serializer):
    identifier = serializers.CharField()
    otp = serializers.CharField()

class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.CharField()
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

#admin notification
class AdminNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminNotification
        fields = '__all__'


# ========== VENDOR & KYC SERIALIZERS ==========
from .models import VendorAccount, KYCVerification

class VendorAccountSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    kyc_status = serializers.SerializerMethodField()
    
    class Meta:
        model = VendorAccount
        fields = [
            'vendor_id', 'user', 'user_details', 'business_name', 'business_type',
            'razorpay_account_id', 'razorpay_linked_account_status',
            'bank_account_number', 'bank_ifsc_code', 'bank_account_holder_name', 'bank_name',
            'account_status', 'kyc_verified', 'kyc_status', 'is_active',
            'commission_percentage', 'created_at', 'updated_at', 'verified_at'
        ]
        read_only_fields = ['vendor_id', 'razorpay_account_id', 'kyc_verified', 'verified_at']
    
    def get_kyc_status(self, obj):
        """Get overall KYC verification status"""
        kyc_docs = obj.kyc_documents.all()
        if not kyc_docs.exists():
            return "not_submitted"
        
        if all(doc.status == 'verified' for doc in kyc_docs):
            return "verified"
        elif any(doc.status == 'rejected' for doc in kyc_docs):
            return "rejected"
        elif any(doc.status == 'in_review' for doc in kyc_docs):
            return "in_review"
        else:
            return "pending"


class KYCVerificationSerializer(serializers.ModelSerializer):
    vendor_details = VendorAccountSerializer(source='vendor', read_only=True)
    reviewed_by_details = UserSerializer(source='reviewed_by', read_only=True)
    
    class Meta:
        model = KYCVerification
        fields = [
            'kyc_id', 'vendor', 'vendor_details', 'document_type', 'document_number',
            'document_file', 'quickekyc_verification_id', 'quickekyc_response',
            'status', 'rejection_reason', 'reviewed_by', 'reviewed_by_details',
            'reviewed_at', 'submitted_at', 'updated_at'
        ]
        read_only_fields = ['kyc_id', 'quickekyc_verification_id', 'quickekyc_response', 
                           'reviewed_at', 'submitted_at']
    
    def validate_document_type(self, value):
        """Ensure vendor doesn't submit duplicate document types"""
        vendor = self.context.get('vendor')
        if vendor and KYCVerification.objects.filter(vendor=vendor, document_type=value).exists():
            if not self.instance:  # Only check on creation, not update
                raise serializers.ValidationError(f"Document type '{value}' already submitted for this vendor.")
        return value


class KYCVerificationCreateSerializer(serializers.ModelSerializer):
    """Simplified serializer for KYC document submission"""
    class Meta:
        model = KYCVerification
        fields = ['vendor', 'document_type', 'document_number', 'document_file']
    
    def create(self, validated_data):
        validated_data['status'] = 'pending'
        return super().create(validated_data)


class VendorAccountCreateSerializer(serializers.ModelSerializer):
    """Simplified serializer for vendor registration"""
    class Meta:
        model = VendorAccount
        fields = ['user', 'business_name', 'business_type', 'bank_account_number', 
                 'bank_ifsc_code', 'bank_account_holder_name', 'bank_name']
    
    def create(self, validated_data):
        validated_data['account_status'] = 'pending'
        validated_data['kyc_verified'] = False
        return super().create(validated_data)

