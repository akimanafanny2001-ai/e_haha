from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Category, CustomerProfile, HomepageImage, Order, Product


class ShopTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name='Fruits',
            slug='fruits',
        )
        self.product = Product.objects.create(
            category=self.category,
            name='Fresh Apples',
            slug='fresh-apples',
            description='Crisp local apples.',
            price=Decimal('5.00'),
            unit='kg',
            stock=3,
            is_available=True,
        )

    def test_home_and_product_pages_work(self):
        response = self.client.get(reverse('shop:home'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, 'Fresh Apples')
        self.assertContains(response, '<div class="ph"></div>', html=True)

    def test_home_uses_fallback_when_no_uploaded_images_exist(self):
        response = self.client.get(reverse('shop:home'))

        self.assertContains(
            response,
            '<div class="hero-product-image hero-feature-image"></div>',
            html=True,
        )

    def test_admin_can_upload_and_publish_homepage_image(self):
        image_bytes = BytesIO()
        Image.new('RGB', (1, 1), color='green').save(image_bytes, format='PNG')
        image_bytes.seek(0)

        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                admin_user = User.objects.create_superuser(
                    username='admin',
                    email='admin@example.com',
                    password='strong-pass-123',
                )
                self.client.force_login(admin_user)
                response = self.client.post(reverse('admin:shop_homepageimage_add'), {
                    'alt_text': 'Fresh fruit display',
                    'is_active': 'on',
                    'sort_order': '0',
                    'image': SimpleUploadedFile(
                        'homepage-fruit.png',
                        image_bytes.getvalue(),
                        content_type='image/png',
                    ),
                })
                self.assertEqual(response.status_code, 302)

                homepage_image = HomepageImage.objects.get(alt_text='Fresh fruit display')
                self.assertTrue(homepage_image.image.storage.exists(homepage_image.image.name))
                home_response = self.client.get(reverse('shop:home'))
                self.assertContains(
                    home_response,
                    f'<img src="{homepage_image.image.url}" alt="Fresh fruit display">',
                    html=True,
                )

    def test_admin_uploaded_product_image_is_displayed(self):
        image_bytes = BytesIO()
        Image.new('RGB', (1, 1), color='green').save(image_bytes, format='PNG')
        image_bytes.seek(0)

        with TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                admin_user = User.objects.create_superuser(
                    username='admin',
                    email='admin@example.com',
                    password='strong-pass-123',
                )
                self.client.force_login(admin_user)
                response = self.client.post(reverse('admin:shop_product_add'), {
                    'category': self.category.id,
                    'name': 'Admin Apples',
                    'slug': 'admin-apples',
                    'description': 'Apples with an uploaded product image.',
                    'price': '4.00',
                    'unit': 'kg',
                    'stock': '5',
                    'is_available': 'on',
                    'image': SimpleUploadedFile(
                        'admin-apples.png',
                        image_bytes.getvalue(),
                        content_type='image/png',
                    ),
                })
                self.assertEqual(response.status_code, 302)

                product = Product.objects.get(slug='admin-apples')
                self.assertTrue(product.image.storage.exists(product.image.name))
                self.assertTrue(product.image.name.startswith('products/'))

                home_response = self.client.get(reverse('shop:home'))
                self.assertContains(
                    home_response,
                    f'<img src="{product.image.url}" alt="Admin Apples">',
                    html=True,
                )
                list_response = self.client.get(reverse('shop:product_list'))
                self.assertContains(
                    list_response,
                    f'<img src="{product.image.url}" alt="Admin Apples">',
                    html=True,
                )
                session = self.client.session
                session['cart'] = {str(product.id): 1}
                session.save()
                cart_response = self.client.get(reverse('shop:cart'))
                self.assertContains(
                    cart_response,
                    f'<img src="{product.image.url}" alt="Admin Apples">',
                    html=True,
                )
                detail_response = self.client.get(product.get_absolute_url())
                self.assertContains(
                    detail_response,
                    f'<img src="{product.image.url}" alt="Admin Apples">',
                    html=True,
                )

    def test_cart_rejects_invalid_and_excess_quantity(self):
        add_url = reverse('shop:add_to_cart', args=[self.product.id])
        response = self.client.post(add_url, {'quantity': '0'})
        self.assertRedirects(response, self.product.get_absolute_url())
        self.assertEqual(self.client.session.get('cart'), None)

        self.client.post(add_url, {'quantity': '99'})
        self.assertEqual(self.client.session['cart'][str(self.product.id)], 3)

    def test_checkout_creates_order_and_updates_stock(self):
        user = User.objects.create_user(
            username='customer',
            password='strong-pass-123',
        )
        self.client.force_login(user)
        self.client.post(
            reverse('shop:add_to_cart', args=[self.product.id]),
            {'quantity': '2'},
        )
        response = self.client.post(reverse('shop:checkout'), {
            'full_name': 'Test Customer',
            'phone': '0780000000',
            'address': '123 Market Road',
            'city': 'Kigali',
        })
        order = Order.objects.get(user=user)
        self.assertRedirects(
            response,
            reverse('shop:order_success', args=[order.id]),
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.total_price, Decimal('10.00'))
        self.assertEqual(self.client.session['cart'], {})

    def test_order_cannot_be_viewed_by_another_user(self):
        owner = User.objects.create_user(username='owner', password='strong-pass-123')
        order = Order.objects.create(
            user=owner,
            full_name='Owner',
            phone='123',
            address='Road',
            city='Kigali',
            total_price=Decimal('5.00'),
        )
        other = User.objects.create_user(username='other', password='strong-pass-123')
        self.client.force_login(other)
        response = self.client.get(reverse('shop:order_detail', args=[order.id]))
        self.assertEqual(response.status_code, 404)

    def test_registration_saves_names_and_profile(self):
        response = self.client.post(reverse('shop:register'), {
            'username': 'newcustomer',
            'first_name': 'New',
            'last_name': 'Customer',
            'email': 'new@example.com',
            'phone': '0781111111',
            'password1': 'Strong-pass-987',
            'password2': 'Strong-pass-987',
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='newcustomer')
        self.assertEqual(user.first_name, 'New')
        self.assertEqual(user.last_name, 'Customer')
        self.assertTrue(CustomerProfile.objects.filter(user=user).exists())
