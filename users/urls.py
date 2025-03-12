from django.urls import path
from .views import  CustomTokenObtainPairView, LogoutView, CustomTokenRefreshView, user_me, SignupView, LoginRequestOTPView, VerifyOTPView, ForgotPasswordRequestOTPView, ResetPasswordView, CreateUserView, AdminUserListView, UpdateShippingAddressView, CustomerLoginRequestOTPView, CustomerVerifyOTPView,CustomerSignupView
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
     path('customer/signup/', CustomerSignupView.as_view(), name='customer-signup'),
    # Customer-specific login with email & OTP
    path('customer/login/', CustomerLoginRequestOTPView.as_view(), name='customer_login_request_otp'),
    path('customer/verify-otp/', CustomerVerifyOTPView.as_view(), name='customer_verify_otp'),
    # User and token related
    path('create-user/', CreateUserView.as_view(), name='create-user'),
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),  # Get access and refresh tokens
    path('token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),  # Refresh access token
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),  # Verify access token
    path('logout/', LogoutView.as_view(), name='logout'),
    path('admin/list/', AdminUserListView.as_view(), name='admin-users-list'),
    path('me/update-shipping/', UpdateShippingAddressView.as_view(), name='update-shipping'),
]

