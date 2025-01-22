# permissions.py
from rest_framework import permissions

class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to allow access only to admin users.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'


class IsStaffUser(permissions.BasePermission):
    """
    Custom permission to allow access only to staff users.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'staff'


class IsCustomerUser(permissions.BasePermission):
    """
    Custom permission to allow access only to customer users.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'customer'


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to allow access only to the owner of the object or admins.
    """
    def has_object_permission(self, request, view, obj):
        # Allow if the user is the owner or an admin
        return obj.user == request.user or request.user.role == 'admin'
