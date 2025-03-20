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
from rest_framework.views import APIView
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist

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
        queryset = Product.objects.all().order_by("name")
        is_active = self.request.query_params.get('is_active', None)
        
        if is_active is not None:
            # Convert 'is_active' to a boolean
            is_active = is_active.lower() in ['true']
            queryset = queryset.filter(is_active=is_active).order_by("name")
        
        return queryset
    
    def list(self, request):
        """ Paginate and return products sorted alphabetically. """
        products = self.get_queryset()  # Get filtered and sorted queryset

        # Paginate the queryset
        paginator = ProductPagination()
        result_page = paginator.paginate_queryset(products, request)

        # Serialize the paginated result
        serializer = ProductSerializer(result_page, many=True, context={'request': request})

        return paginator.get_paginated_response(serializer.data)

    def destroy(self, request, pk=None):
        """ Soft delete: Set `is_active` to False and update related favorites. """
        product = Product.objects.filter(product_id=pk, is_active=True).first()
        
        if product:
            # Mark product as inactive
            product.is_active = False
            product.save()

            # Mark all related favorites as inactive
            Favorite.objects.filter(product=product, is_active=True).update(is_active=False)

            # Check if the associated category has any active products
            category = product.category
            if category and not category.products.filter(is_active=True).exists():
                category.is_active = False
                category.save()

            return Response({"message": "Product and its favorites marked as inactive"}, status=status.HTTP_204_NO_CONTENT)
        
        return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

    def create(self, request, *args, **kwargs):
        """ Create a product and ensure its category is active """
        response = super().create(request, *args, **kwargs)  # Let DRF handle the creation
        product_id = response.data.get("product_id")  # Get the new product's ID
         # Ensure its category is active
        product = Product.objects.filter(product_id=product_id).first()
        if product and product.category:
            product.category.is_active = True
            product.category.save()
           
        return response    

    
    def update(self, request, *args, **kwargs):
        """ Update product  """
        response = super().update(request, *args, **kwargs)
        return response



class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by("name")
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
        queryset = Category.objects.all().order_by("name")
        is_active = self.request.query_params.get('is_active', None)
        
        if is_active is not None:
            is_active = is_active.lower() in ['true']
            queryset = queryset.filter(is_active=is_active).order_by("name")
        
        return queryset

    def list(self, request):
        """ Paginate and return categories sorted alphabetically. """
        categories = self.get_queryset()
        paginator = ProductPagination()
        result_page = paginator.paginate_queryset(categories, request)
        serializer = CategorySerializer(result_page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        """ 
        Handles category creation:
        - If a category with the same `category_code`, `name`, and `description` is active → Return an error.
        - If a category with the same values exists but is inactive → Reactivate it.
        - Otherwise, create a new category.
        """
        data = request.data.copy()
        category_code = data.get("category_code", "").strip()
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()

        if not category_code:
            return Response({"error": "category_code is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Check if a category with the same `category_code`, `name`, and `description` exists
        existing_category = Category.objects.filter(category_code=category_code, name=name, description=description).first()

        if existing_category:
            if existing_category.is_active:
                return Response({"error": "Category with this category_code, name, and description already exists and is active."}, status=status.HTTP_400_BAD_REQUEST)
            else:
                # Reactivate and update if necessary
                existing_category.is_active = True
                existing_category.save()
                return Response(CategorySerializer(existing_category, context={"request": request}).data, status=status.HTTP_200_OK)

        # If no exact match exists, create a new category
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """ 
        Update category and ensure products follow the category's state.
        Prevents duplicate name-description combinations.
        """
        category = self.get_object()
        data = request.data.copy()  # Make a copy of request data

        new_category_code = data.get("category_code", category.category_code).strip()
        new_name = data.get("name", category.name).strip()
        new_description = data.get("description", category.description).strip()
        is_active = data.get("is_active", category.is_active)  # Get the new state

        # Prevent duplicate combination of `category_code`, `name`, and `description`
        if Category.objects.exclude(category_id=category.category_id).filter(
            category_code=new_category_code, name=new_name, description=new_description, is_active=True
        ).exists():
            return Response({"error": "Category with this category_code, name, and description already exists."}, status=status.HTTP_400_BAD_REQUEST)

        # Update category
        category.category_code = new_category_code
        category.name = new_name
        category.description = new_description
        category.is_active = is_active
        category.save()

        # If category is deactivated, deactivate its products
        if not category.is_active:
            Product.objects.filter(category=category).update(is_active=False)

        return Response(CategorySerializer(category, context={'request': request}).data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        """ 
        Soft delete: Set `is_active = False` for the category and its associated products.
        """
        category = self.get_object()
        category.is_active = False
        category.save()

        # Also deactivate all related products
        Product.objects.filter(category=category).update(is_active=False)

        return Response({"message": "Category and associated products marked as inactive"}, status=status.HTTP_204_NO_CONTENT)


class FavoriteViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = ProductPagination  # Add this line to use pagination

    def get_queryset(self):
        """
        Optionally filter favorites by 'is_active' query param.
        If 'is_active' is provided, filter based on its value.
        """
        queryset = Favorite.objects.filter(user=self.request.user).order_by("product__name")
        is_active = self.request.query_params.get('is_active', None)
        
        if is_active is not None:
            # Convert 'is_active' to a boolean
            is_active = is_active.lower() in ['true']
            queryset = queryset.filter(is_active=is_active).order_by("product__name")
        
        return queryset

    def list(self, request):
        """ Get all favorite products for the user, with optional pagination and filtering """
        favorites = self.get_queryset()  # Apply filters here
        
        # Paginate the queryset
        paginator = ProductPagination()
        result_page = paginator.paginate_queryset(favorites, request)
        
        # Serialize the paginated result, passing the request context
        serializer = FavoriteSerializer(result_page, many=True, context={'request': request})
        
        # Return paginated response
        return paginator.get_paginated_response(serializer.data)

    def create(self, request):
        """ Add a product to favorites (reactivate if soft deleted) """
        product_id = request.data.get("product_id")
        product = Product.objects.filter(product_id=product_id, is_active = True).first()
        
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

    def get_serializer_context(self):
        """
        Ensure that request is passed into the serializer context for URL building.
        """
        context = super().get_serializer_context()
        context['request'] = self.request  # Add the current request to the context
        return context


class UploadedImageViewSet(viewsets.ModelViewSet):
    queryset = UploadedImage.objects.all()
    serializer_class = UploadedImageSerializer
    permission_classes = [IsAuthenticated, IsAdminUser | IsStaffUser]  # Only admins/staff can upload images
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
        """ Handle image upload with product/category validation """
        file = request.FILES.get('image')
        product_id = request.data.get("product")
        category_id = request.data.get("category")

        # Ensure an image is provided
        if not file:
            return Response({"error": "No image provided."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate file type (only PNG)
        if not file.name.lower().endswith('.png'):
            return Response({"error": "Only PNG images are allowed."}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure only one foreign key is set
        if product_id and category_id:
            return Response({"error": "An image cannot be linked to both a product and a category."}, status=status.HTTP_400_BAD_REQUEST)

        product, category = None, None

        # Validate product existence and active status
        if product_id:
            try:
                product = Product.objects.get(pk=product_id, is_active=True)
            except ObjectDoesNotExist:
                return Response({"error": "Product does not exist or is inactive."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate category existence and active status
        elif category_id:
            try:
                category = Category.objects.get(pk=category_id, is_active=True)
            except ObjectDoesNotExist:
                return Response({"error": "Category does not exist or is inactive."}, status=status.HTTP_400_BAD_REQUEST)

        # If neither a valid product nor category is found, reject the request
        if not product and not category:
            return Response({"error": "Either a valid product or category must be provided."}, status=status.HTTP_400_BAD_REQUEST)

        # Save the image with the valid product/category
        uploaded_image = UploadedImage.objects.create(image=file, product=product, category=category)
        serializer = self.get_serializer(uploaded_image)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """ Updates an image file and ensures only one foreign key (Product or Category) is set. """
        instance = self.get_object()
        product_id = request.data.get("product")
        category_id = request.data.get("category")
        new_image = request.FILES.get("image")  # Get new image file

        # Handle foreign key updates
        if product_id:
            try:
                product = Product.objects.get(pk=product_id, is_active=True)
            except ObjectDoesNotExist:
                return Response({"error": "Product does not exist or is inactive."}, status=status.HTTP_400_BAD_REQUEST)
            instance.product = product
            instance.category = None  # Unlink category

        elif category_id:
            try:
                category = Category.objects.get(pk=category_id, is_active=True)
            except ObjectDoesNotExist:
                return Response({"error": "Category does not exist or is inactive."}, status=status.HTTP_400_BAD_REQUEST)
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
        """ Delete an image and remove it from the filesystem """
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


class SearchViewSet(APIView):
    pagination_class = ProductPagination  # Use existing pagination

    def post(self, request, *args, **kwargs):
        query = request.data.get("query", "").strip()  # Read query from JSON body

        if not query:
            return Response({"error": "Query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Search in products
        product_results = Product.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query),
            is_active=True
        ).order_by("name")

        # Search in categories
        category_results = Category.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query),
            is_active=True
        ).order_by("name")

        # Initialize pagination
        paginator = self.pagination_class()

        # Paginate products
        paginated_products = paginator.paginate_queryset(product_results, request)
        paginated_categories = paginator.paginate_queryset(category_results, request)

        # Serialize paginated results
        product_serializer = ProductSerializer(paginated_products, many=True, context={"request": request})
        category_serializer = CategorySerializer(paginated_categories, many=True, context={"request": request})

        return Response({
            "products": {
                "count": product_results.count(),
                "results": product_serializer.data,
            },
            "categories": {
                "count": category_results.count(),
                "results": category_serializer.data,
            }
        }, status=status.HTTP_200_OK)