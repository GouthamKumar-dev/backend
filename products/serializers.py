from rest_framework import serializers
from .models import Product, Category, Favorite, UploadedImage

class CategorySerializer(serializers.ModelSerializer):
    images = serializers.SerializerMethodField()  # New field to include image URLs

    class Meta:
        model = Category
        fields = '__all__'

    def get_images(self, obj):
        """ Fetch all image URLs related to this category or product """
        request = self.context.get("request")
        # Check if the object is Category or Product and fetch associated images accordingly
        images = UploadedImage.objects.filter(category=obj) if isinstance(obj, Category) else UploadedImage.objects.filter(product=obj)

        if request:
            return [request.build_absolute_uri(img.image.url) for img in images if img.image]
        return [img.image.url for img in images if img.image]  # Use relative URL if request is None

class ProductSerializer(serializers.ModelSerializer):
    category = serializers.SerializerMethodField()  # Use SerializerMethodField for filtering
    favorite_count = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    offer_price = serializers.SerializerMethodField()  # Dynamically fetched


    class Meta:
        model = Product
        fields = [
            "product_id",
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
        if obj.discount_percentage:  # Ensure discount exists
            return obj.price * (1 - obj.discount_percentage / 100)
        return obj.price
       

    def get_category(self, obj):
        """ Fetch only active categories """
        if obj.category and obj.category.is_active:
            return CategorySerializer(obj.category, context=self.context).data
        return None  # Return None if category is inactive

    def get_favorite_count(self, obj):
        return obj.favorite_count()

    def get_images(self, obj):
        """ Fetch all image URLs related to this product """
        request = self.context.get("request")
        images = UploadedImage.objects.filter(product=obj)

        if request:
            return [request.build_absolute_uri(img.image.url) for img in images if img.image]
        return [img.image.url for img in images if img.image]  # Use relative URL if request is None

    def handle_category(self, category_data):
        """Handles category logic: reuse, reactivate, or create a new one."""
        name = category_data.get("name", "").strip()
        description = category_data.get("description", "").strip()

        # Check if an active category with the same name & description exists
        existing_active_category = Category.objects.filter(name=name, description=description, is_active=True).first()
        if existing_active_category:
            return existing_active_category  # Use existing active category

        # Check if an inactive category with the same name & description exists
        existing_inactive_category = Category.objects.filter(name=name, description=description, is_active=False).first()
        if existing_inactive_category:
            existing_inactive_category.is_active = True  # Reactivate category
            existing_inactive_category.save()
            return existing_inactive_category

        # Create a new category if none exists
        return Category.objects.create(name=name, description=description, is_active=True)

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
        fields = ['id','image', 'product', 'category', 'uploaded_at']

    def get_image_url(self, obj):
        """ Generate a URL for the stored image """
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None
