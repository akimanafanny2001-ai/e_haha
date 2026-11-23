from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Category, CustomerProfile, Order, Product


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
