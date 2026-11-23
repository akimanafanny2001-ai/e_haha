from django.core.management.base import BaseCommand

from shop.models import Category, Product


class Command(BaseCommand):
    help = 'Create a small set of demo categories and products.'

    def handle(self, *args, **options):
        catalog = {
            'Fruits': [
                ('Fresh Apples', 'fresh-apples', 'Crisp locally sourced apples.', '3.50', 'kg', 25),
                ('Sweet Bananas', 'sweet-bananas', 'Naturally sweet ripe bananas.', '2.20', 'kg', 40),
                ('Oranges', 'oranges', 'Juicy vitamin-rich oranges.', '4.00', 'kg', 30),
            ],
            'Vegetables': [
                ('Tomatoes', 'tomatoes', 'Fresh red tomatoes.', '2.80', 'kg', 35),
                ('Broccoli', 'broccoli', 'Tender green broccoli heads.', '3.20', 'piece', 20),
                ('Carrots', 'carrots', 'Crunchy fresh carrots.', '2.40', 'kg', 28),
            ],
            'Dairy & Eggs': [
                ('Fresh Milk', 'fresh-milk', 'Fresh pasteurized whole milk.', '1.80', 'liter', 30),
                ('Free-range Eggs', 'free-range-eggs', 'A tray of twelve free-range eggs.', '5.50', 'tray', 18),
            ],
            'Bakery': [
                ('Wholegrain Bread', 'wholegrain-bread', 'Freshly baked wholegrain loaf.', '2.50', 'loaf', 20),
                ('Croissants', 'croissants', 'Buttery breakfast croissants.', '4.20', 'pack', 15),
            ],
        }

        created_categories = 0
        created_products = 0
        for category_name, products in catalog.items():
            category, created = Category.objects.get_or_create(
                name=category_name,
                defaults={'slug': category_name.lower().replace(' & ', '-').replace(' ', '-')},
            )
            if created:
                created_categories += 1
            for name, slug, description, price, unit, stock in products:
                _, created = Product.objects.get_or_create(
                    slug=slug,
                    defaults={
                        'category': category,
                        'name': name,
                        'description': description,
                        'price': price,
                        'unit': unit,
                        'stock': stock,
                        'is_available': True,
                        'is_featured': created_products % 3 == 0,
                    },
                )
                if created:
                    created_products += 1

        self.stdout.write(self.style.SUCCESS(
            f'Seed complete: {created_categories} categories and {created_products} products added.'
        ))
