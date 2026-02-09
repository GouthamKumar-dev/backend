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

class IsAdminOrStaff(permissions.BasePermission):
    """
    Custom permission to allow only Admins and Staff to create, update, or delete products and categories.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['admin', 'staff']


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to allow only the owner of an object to modify it.
    Other users can only read (GET) the object.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True  # Read-only access
        return obj.user == request.user  # Modify only if the user owns it
