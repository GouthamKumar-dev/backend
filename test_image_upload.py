#!/usr/bin/env python
"""
Test script for image upload functionality
Tests category and product image uploads
"""
import os
import sys
import django
from io import BytesIO
from PIL import Image

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ecommerce.settings')
django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile
from products.models import Category, Product, UploadedImage
from users.models import CustomUser

def create_test_image(filename='test.png', size=(100, 100), color='red'):
    """Create a test image in memory"""
    image = Image.new('RGB', size, color)
    file = BytesIO()
    image.save(file, 'PNG')
    file.seek(0)
    return SimpleUploadedFile(
        filename,
        file.read(),
        content_type='image/png'
    )

def test_category_image_upload():
    """Test category image upload"""
    print("\n" + "="*60)
    print("Testing Category Image Upload")
    print("="*60)
    
    # Create or get test category
    category, created = Category.objects.get_or_create(
        category_code='TEST_CAT_001',
        defaults={
            'name': 'Test Category',
            'description': 'Category for testing image uploads',
            'is_active': True
        }
    )
    
    if created:
        print(f"✓ Created test category: {category.name}")
    else:
        print(f"✓ Using existing category: {category.name}")
    
    # Create test images
    normal_image = create_test_image('category_normal.png', color='blue')
    carousel_image = create_test_image('category_carousel.png', color='green')
    
    # Upload normal image
    try:
        uploaded_normal = UploadedImage.objects.create(
            image=normal_image,
            category=category,
            type='normal'
        )
        print(f"✓ Normal image uploaded: {uploaded_normal.image.url}")
    except Exception as e:
        print(f"✗ Failed to upload normal image: {str(e)}")
        return False
    
    # Upload carousel image
    try:
        uploaded_carousel = UploadedImage.objects.create(
            image=carousel_image,
            category=category,
            type='carousel'
        )
        print(f"✓ Carousel image uploaded: {uploaded_carousel.image.url}")
    except Exception as e:
        print(f"✗ Failed to upload carousel image: {str(e)}")
        return False
    
    # Verify images exist
    category_images = UploadedImage.objects.filter(category=category)
    print(f"✓ Total images for category: {category_images.count()}")
    
    for img in category_images:
        file_path = img.image.path
        if os.path.exists(file_path):
            print(f"  - {img.type}: {file_path} (exists)")
        else:
            print(f"  - {img.type}: {file_path} (MISSING!)")
    
    return True

def test_product_image_upload():
    """Test product image upload"""
    print("\n" + "="*60)
    print("Testing Product Image Upload")
    print("="*60)
    
    # Get or create admin user
    try:
        admin = CustomUser.objects.filter(role='admin').first()
        if not admin:
            print("✗ No admin user found. Creating test admin...")
            admin = CustomUser.objects.create_user(
                username='test_admin',
                email='testadmin@test.com',
                password='test123',
                role='admin',
                phone_number='1234567890'
            )
    except Exception as e:
        print(f"✗ Error getting admin: {str(e)}")
        return False
    
    # Get or create test category
    category = Category.objects.filter(category_code='TEST_CAT_001').first()
    if not category:
        print("✗ Test category not found")
        return False
    
    # Create or get test product
    product, created = Product.objects.get_or_create(
        product_code='TEST_PROD_001',
        defaults={
            'name': 'Test Product',
            'description': 'Product for testing image uploads',
            'price': 99.99,
            'stock': 10,
            'category': category,
            'admin': admin,
            'is_active': True
        }
    )
    
    if created:
        print(f"✓ Created test product: {product.name}")
    else:
        print(f"✓ Using existing product: {product.name}")
    
    # Create test images
    normal_image = create_test_image('product_normal.png', color='red')
    carousel_image = create_test_image('product_carousel.png', color='yellow')
    
    # Upload normal image
    try:
        uploaded_normal = UploadedImage.objects.create(
            image=normal_image,
            product=product,
            type='normal'
        )
        print(f"✓ Normal image uploaded: {uploaded_normal.image.url}")
    except Exception as e:
        print(f"✗ Failed to upload normal image: {str(e)}")
        return False
    
    # Upload carousel image
    try:
        uploaded_carousel = UploadedImage.objects.create(
            image=carousel_image,
            product=product,
            type='carousel'
        )
        print(f"✓ Carousel image uploaded: {uploaded_carousel.image.url}")
    except Exception as e:
        print(f"✗ Failed to upload carousel image: {str(e)}")
        return False
    
    # Verify images exist
    product_images = UploadedImage.objects.filter(product=product)
    print(f"✓ Total images for product: {product_images.count()}")
    
    for img in product_images:
        file_path = img.image.path
        if os.path.exists(file_path):
            print(f"  - {img.type}: {file_path} (exists)")
        else:
            print(f"  - {img.type}: {file_path} (MISSING!)")
    
    return True

def check_media_directory():
    """Check if media directory exists and has proper permissions"""
    print("\n" + "="*60)
    print("Checking Media Directory Setup")
    print("="*60)
    
    from django.conf import settings
    
    media_root = settings.MEDIA_ROOT
    media_url = settings.MEDIA_URL
    
    print(f"MEDIA_ROOT: {media_root}")
    print(f"MEDIA_URL: {media_url}")
    
    if os.path.exists(media_root):
        print(f"✓ Media directory exists")
        
        # Check permissions
        if os.access(media_root, os.W_OK):
            print(f"✓ Media directory is writable")
        else:
            print(f"✗ Media directory is NOT writable")
            return False
    else:
        print(f"✗ Media directory does NOT exist")
        print(f"  Creating: {media_root}")
        try:
            os.makedirs(media_root, exist_ok=True)
            print(f"✓ Media directory created")
        except Exception as e:
            print(f"✗ Failed to create media directory: {str(e)}")
            return False
    
    # Check uploads subdirectory
    uploads_dir = os.path.join(media_root, 'uploads')
    if os.path.exists(uploads_dir):
        print(f"✓ Uploads directory exists")
    else:
        print(f"  Creating uploads directory: {uploads_dir}")
        try:
            os.makedirs(uploads_dir, exist_ok=True)
            print(f"✓ Uploads directory created")
        except Exception as e:
            print(f"✗ Failed to create uploads directory: {str(e)}")
            return False
    
    return True

def main():
    print("\n" + "="*60)
    print("IMAGE UPLOAD FUNCTIONALITY TEST")
    print("="*60)
    
    # Step 1: Check media directory
    if not check_media_directory():
        print("\n✗ Media directory setup failed!")
        return
    
    # Step 2: Test category image upload
    if not test_category_image_upload():
        print("\n✗ Category image upload test failed!")
        return
    
    # Step 3: Test product image upload
    if not test_product_image_upload():
        print("\n✗ Product image upload test failed!")
        return
    
    print("\n" + "="*60)
    print("✓ ALL TESTS PASSED!")
    print("="*60)
    print("\nImage upload functionality is working correctly.")
    print("You can now upload images when creating/editing categories and products.")

if __name__ == '__main__':
    main()
