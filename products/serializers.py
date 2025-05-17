from rest_framework import serializers
from .models import Product, Category, Favorite, UploadedImage

class CategorySerializer(serializers.ModelSerializer):
    images = serializers.SerializerMethodField()  # New field to include image URLs

    class Meta:
        model = Category
        fields = '__all__'

    def get_images(self, obj):
        """Fetch all image URLs related to this category or product, including their type."""
        request = self.context.get("request")
        images = UploadedImage.objects.filter(category=obj) if isinstance(obj, Category) else UploadedImage.objects.filter(product=obj)

        result = []
        for img in images:
            if img.image:
                image_url = request.build_absolute_uri(img.image.url) if request else img.image.url
                result.append({
                    "id": img.id,
                    "url": image_url,
                    "type": img.type  # 'normal' or 'carousel'
                })

        return result


class ProductSerializer(serializers.ModelSerializer):
    category = serializers.SerializerMethodField()  # Use SerializerMethodField for filtering
    favorite_count = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    offer_price = serializers.SerializerMethodField()  # Dynamically fetched


    class Meta:
        model = Product
        fields = [
            "product_id",
            "product_code",  # Include product_code in the fields
            "name",
            "description",
            "price",
            "discount_percentage",  # NEW: Added discount percentage
            "offer_price",
            "stock",
            "category",  # Now fetched with filtering
            "created_at",
            "updated_at",
            "is_active",
            "favorite_count",
            "images",
        ]
        
    def get_offer_price(self, obj):
        """Calculate offer price dynamically using discount_percentage."""
        return obj.offer_price
       

    def get_category(self, obj):
        """ Fetch only active categories """
        if obj.category and obj.category.is_active:
            return CategorySerializer(obj.category, context=self.context).data
        return None  # Return None if category is inactive

    def get_favorite_count(self, obj):
        return obj.favorite_count()

    def get_images(self, obj):
        request = self.context.get("request")
        images = UploadedImage.objects.filter(product=obj)

        result = []
        for img in images:
            if img.image:
                image_url = request.build_absolute_uri(img.image.url) if request else img.image.url
                result.append({
                    "id": img.id,
                    "url": image_url,
                    "type": img.type  # normal or carousel
                })

        return result


    def handle_category(self, category_data):
        """Handles category logic: reuse, reactivate, or create a new one."""
        name = category_data.get("name", "").strip()
        description = category_data.get("description", "").strip()
        category_code = category_data.get("category_code", "").strip()

        if not category_code:
            raise serializers.ValidationError("Category code is required.")

        # Check if an active category exists with the same category_code
        existing_active_category = Category.objects.filter(category_code=category_code, is_active=True).first()

        if existing_active_category:
            # Ensure name and description match; otherwise, return an error
            if existing_active_category.name != name or existing_active_category.description != description:
                raise serializers.ValidationError(f"Category code '{category_code}' already exists but with different details.")
            return existing_active_category  # Use existing category

        # Check if an inactive category exists with the same category_code
        existing_inactive_category = Category.objects.filter(category_code=category_code, is_active=False).first()

        if existing_inactive_category:
            # Update name, description, and reactivate
            existing_inactive_category.name = name
            existing_inactive_category.description = description
            existing_inactive_category.is_active = True
            existing_inactive_category.save()
            return existing_inactive_category

        # Create a new category if none exists
        return Category.objects.create(name=name, description=description, category_code=category_code, is_active=True)

    def create(self, validated_data):
        category_data = self.initial_data.get("category", None)  # Use initial_data to get nested dict
        category = None

        if category_data:
            category = self.handle_category(category_data)  # Call the category handling logic

        product_code = validated_data.get("product_code", "").strip()

        # 🔹 Check if a product with the same product_code already exists
        existing_product = Product.objects.filter(product_code=product_code).first()

        if existing_product:
            if existing_product.is_active:
                raise serializers.ValidationError(f"A product with product_code '{product_code}' already exists and is active.")
            else:
                # 🔹 Reactivate the inactive product
                existing_product.is_active = True
                existing_product.name = validated_data.get("name", existing_product.name)
                existing_product.description = validated_data.get("description", existing_product.description)
                existing_product.price = validated_data.get("price", existing_product.price)
                existing_product.stock = validated_data.get("stock", existing_product.stock)
                existing_product.category = category or existing_product.category  # Update category if provided
                existing_product.save()
                return existing_product  # Return the reactivated product

        # 🔹 If no existing product, create a new one
        validated_data["category"] = category
        return Product.objects.create(**validated_data)


    def update(self, instance, validated_data):
        category_data = self.initial_data.get("category", None)

        if category_data:
            category = self.handle_category(category_data)  # Call the category handling logic
            instance.category = category

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance



class FavoriteSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)  # Nested product details
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(), source='product', write_only=True
    )

    class Meta:
        model = Favorite
        fields = ['favorite_id', 'user', 'product', 'product_id', 'is_active']
        read_only_fields = ['favorite_id', 'user']


class UploadedImageSerializer(serializers.ModelSerializer):

    class Meta:
        model = UploadedImage
        fields = ['id','image', 'product','type', 'category', 'uploaded_at']

    def get_image_url(self, obj):
        """ Generate a URL for the stored image """
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None
