from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated,AllowAny
from .models import Product, Category, Favorite, UploadedImage
from django.shortcuts import get_object_or_404
from .serializers import ProductSerializer, CategorySerializer, FavoriteSerializer, UploadedImageSerializer
from rest_framework.pagination import PageNumberPagination
from users.permissions import *
import os

class ProductPagination(PageNumberPagination):
    page_size = 10  # Number of items per page (change as needed)
    page_size_query_param = 'page_size'  # Allows clients to set page size dynamically
    max_page_size = 100  # Prevents very large queries

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    pagination_class = ProductPagination
    http_method_names = ['get', 'post', 'delete', 'put']
    permission_classes = [IsAuthenticated]  # Default for all methods

    def get_permissions(self):
        """ Assign different permissions for different actions. """
        if self.action in ['create', 'update', 'destroy']:  # Admins/Staff only
            self.permission_classes = [IsAuthenticated, IsAdminOrStaff]
        else:  # Anyone can read
            self.permission_classes = [permissions.AllowAny]
        return super().get_permissions()

    def get_queryset(self):
        """ Optionally filter products by 'is_active' query param. """
        queryset = Product.objects.all()
        is_active = self.request.query_params.get('is_active', None)
        
        if is_active is not None:
            # Convert 'is_active' to a boolean
            is_active = is_active.lower() in ['true']
            queryset = queryset.filter(is_active=is_active)
        
        return queryset

    def destroy(self, request, pk=None):
        """ Soft delete: Set `is_active` to False. """
        product = Product.objects.filter(product_id=pk).first()
        
        if product:
            product.is_active = False
            product.save()

            # Check if the associated category has any active products
            category = product.category
            if category and not category.products.filter(is_active=True).exists():
                category.is_active = False
                category.save()

            return Response({"message": "Product marked as inactive"}, status=status.HTTP_204_NO_CONTENT)
        
        return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

    def create(self, request, *args, **kwargs):
        """ Create a product and ensure its category is active """
        response = super().create(request, *args, **kwargs)  # Let DRF handle the creation
        product_id = response.data.get("product_id")  # Get the new product's ID
        
        product = Product.objects.filter(product_id=product_id).first()
        if product and product.category:
            product.category.is_active = True
            product.category.save()

        return response


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    pagination_class = ProductPagination
    http_method_names = ['get', 'post', 'delete', 'put']
    permission_classes = [IsAuthenticated]  # Default permission

    def get_permissions(self):
        """ Assign different permissions for different actions. """
        if self.action in ['create', 'update', 'destroy']:  # Only Admins/Staff
            self.permission_classes = [IsAuthenticated, IsAdminOrStaff]
        else:  # Anyone can read
            self.permission_classes = [permissions.AllowAny]
        return super().get_permissions()

    def get_queryset(self):
        """
        Optionally filter categories by 'is_active' query param.
        If 'is_active' is provided, filter based on its value.
        """
        queryset = Category.objects.all()
        is_active = self.request.query_params.get('is_active', None)
        
        if is_active is not None:
            # Convert 'is_active' to a boolean
            is_active = is_active.lower() in ['true']
            queryset = queryset.filter(is_active=is_active)
        
        return queryset

    def destroy(self, request, *args, **kwargs):
        """ Soft delete: Set isActive to False """
        category = self.get_object()
        category.is_active = False  # Set the 'is_active' field to False
        category.save()
        return Response({"message": "Category marked as inactive"}, status=status.HTTP_204_NO_CONTENT)

class FavoriteViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = ProductPagination  # Add this line to use pagination

    def get_queryset(self):
        """
        Optionally filter favorites by 'is_active' query param.
        If 'is_active' is provided, filter based on its value.
        """
        queryset = Favorite.objects.filter(user=self.request.user)
        is_active = self.request.query_params.get('is_active', None)
        
        if is_active is not None:
            # Convert 'is_active' to a boolean
            is_active = is_active.lower() in ['true']
            queryset = queryset.filter(is_active=is_active)
        
        return queryset

    def list(self, request):
        """ Get all favorite products for the user, with optional pagination and filtering """
        favorites = self.get_queryset()  # Apply filters here
        
        # Paginate the queryset
        paginator = ProductPagination()
        result_page = paginator.paginate_queryset(favorites, request)
        
        # Serialize the paginated result
        serializer = FavoriteSerializer(result_page, many=True)
        
        # Return paginated response
        return paginator.get_paginated_response(serializer.data)

    def create(self, request):
        """ Add a product to favorites (reactivate if soft deleted) """
        product_id = request.data.get("product_id")
        product = Product.objects.filter(product_id=product_id).first()
        
        if not product:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Check if a soft-deleted favorite exists
        favorite = Favorite.objects.filter(user=request.user, product=product).first()
        
        if favorite:
            if not favorite.is_active:
                favorite.is_active = True  # Reactivate the favorite
                favorite.save()
                return Response({"message": "Product re-added to favorites"}, status=status.HTTP_200_OK)
            return Response({"message": "Product already in favorites"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Create new favorite if none exists
        Favorite.objects.create(user=request.user, product=product, is_active=True)
        return Response({"message": "Product added to favorites"}, status=status.HTTP_201_CREATED)


    def destroy(self, request, pk=None):
        """ Soft delete: Set isActive to False """
        favorite = Favorite.objects.filter(user=request.user, product_id=pk).first()
        
        if favorite:
            favorite.is_active = False  # Set the 'is_active' field to False
            favorite.save()
            return Response({"message": "Product removed from favorites"}, status=status.HTTP_204_NO_CONTENT)
        
        return Response({"error": "Favorite not found"}, status=status.HTTP_404_NOT_FOUND)

class UploadedImageViewSet(viewsets.ModelViewSet):
    queryset = UploadedImage.objects.all()
    serializer_class = UploadedImageSerializer
    permission_classes = [IsAuthenticated, IsAdminUser | IsStaffUser]  # Only authenticated users can upload images
    pagination_class = ProductPagination
    parser_classes = [MultiPartParser, FormParser]  # Handle file uploads
    http_method_names = ['get', 'post', 'delete', 'put']

    def get_queryset(self):
        """
        Filters images based on 'type' query param.
        Example: /api/products/images/?type=product or ?type=category
        """
        queryset = UploadedImage.objects.all()
        image_type = self.request.query_params.get('type', None)  # Get query param

        if image_type == 'product':
            queryset = queryset.filter(product__isnull=False)  # Filter images related to products
        elif image_type == 'category':
            queryset = queryset.filter(category__isnull=False)  # Filter images related to categories

        return queryset

    def create(self, request, *args, **kwargs):
        """ Handle image upload """
        file = request.FILES.get('image')

        if not file:
            return Response({"error": "No image provided."}, status=status.HTTP_400_BAD_REQUEST)

        if not file.name.endswith('.png'):
            return Response({"error": "Only PNG images are allowed."}, status=status.HTTP_400_BAD_REQUEST)

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """ Updates an image file and ensures only one foreign key (Product or Category) is set. """
        instance = self.get_object()
        product_id = request.data.get("product")
        category_id = request.data.get("category")
        new_image = request.FILES.get("image")  # Get new image file

        # Handle foreign key updates
        if product_id:
            product = get_object_or_404(Product, pk=product_id)
            instance.product = product
            instance.category = None  # Unlink category

        elif category_id:
            category = get_object_or_404(Category, pk=category_id)
            instance.category = category
            instance.product = None  # Unlink product

        # Replace existing image if a new one is provided
        if new_image:
            # Delete old image from filesystem
            if instance.image:
                old_image_path = instance.image.path
                if os.path.exists(old_image_path):
                    os.remove(old_image_path)  # Delete old file

            # Save new image
            instance.image = new_image

        instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        # Get the image instance based on the provided ID
        try:
            image = self.get_object()
        except ObjectDoesNotExist:
            return Response({"error": "Image not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Delete the image file from the filesystem
        if image.image:
            image_path = image.image.path  # Get the file path of the image
            try:
                os.remove(image_path)  # Delete the image file from the server
            except FileNotFoundError:
                pass  # If the file is not found, just continue

        # Now, delete the image from the database
        image.delete()

        return Response({"message": "Image deleted successfully"}, status=status.HTTP_204_NO_CONTENT)