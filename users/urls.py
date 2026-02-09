from django.urls import path
from .views import (
    CustomTokenObtainPairView, LogoutView, CustomTokenRefreshView, user_me, 
    SignupView, LoginRequestOTPView, VerifyOTPView, ForgotPasswordRequestOTPView, 
    ResetPasswordView, CreateUserView, AdminUserListView, UpdateShippingAddressView, 
    CustomerLoginRequestOTPView, AdminNotificationListView, DeleteAccountRequestOTPView, 
    DeleteAccountVerifyView,
    # Owner dashboard views
    owner_dashboard, owner_payment_history, owner_audit_log, owner_list_admins,
    # Bank details management
    manage_bank_details, owner_list_admins_bank_details, owner_verify_bank_details
)
from rest_framework_simplejwt.views import TokenVerifyView

urlpatterns = [
    # my profile only
    path('me/', user_me, name='user-me'),
    # Add token creation, signup, login, and logout endpoints
    # Login related
    path('signup/', SignupView.as_view(), name='signup'),
    path('login/', LoginRequestOTPView.as_view(), name='login_request_otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
    path('forgot-password/', ForgotPasswordRequestOTPView.as_view(), name='forgot_password_request_otp'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset_password'),
    # Customer-specific login with email & OTP
    path('customer/login/', CustomerLoginRequestOTPView.as_view(), name='customer_login_request_otp'),
    # Delete account endpoints
    path('delete-account/request/', DeleteAccountRequestOTPView.as_view(), name='delete_account_request_otp'),
    path('delete-account/verify/', DeleteAccountVerifyView.as_view(), name='delete_account_verify'),
    # User and token related
    path('create-user/', CreateUserView.as_view(), name='create-user'),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),  # Get access and refresh tokens
    path('token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),  # Refresh access token
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),  # Verify access token
    path('logout/', LogoutView.as_view(), name='logout'),
    path('admin/list/', AdminUserListView.as_view(), name='admin-users-list'),
    path('me/update-shipping/', UpdateShippingAddressView.as_view(), name='update-shipping'),
    path('admin/notifications/', AdminNotificationListView.as_view(), name='admin-notifications-list'),
    
    # ========== OWNER DASHBOARD ==========
    path('owner/dashboard/', owner_dashboard, name='owner_dashboard'),
    path('owner/payment-history/', owner_payment_history, name='owner_payment_history'),
    path('owner/audit-log/', owner_audit_log, name='owner_audit_log'),
    path('owner/admins/', owner_list_admins, name='owner_list_admins'),
    
    # ========== BANK DETAILS MANAGEMENT ==========
    path('bank-details/', manage_bank_details, name='manage_bank_details'),  # Admin: GET/PUT their bank details
    path('owner/bank-details/', owner_list_admins_bank_details, name='owner_list_admins_bank_details'),  # Owner: View all
    path('owner/bank-details/<int:admin_id>/verify/', owner_verify_bank_details, name='owner_verify_bank_details'),  # Owner: Verify
]


