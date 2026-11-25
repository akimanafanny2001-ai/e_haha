from django.contrib import admin
from .models import Category, HomepageImage, Product, CustomerProfile, Order, OrderItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'created_at']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'unit', 'stock', 'is_available', 'is_featured']
    list_filter = ['is_available', 'is_featured', 'category']
    list_editable = ['price', 'stock', 'is_available', 'is_featured']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name', 'description']


@admin.register(HomepageImage)
class HomepageImageAdmin(admin.ModelAdmin):
    list_display = ['alt_text', 'is_active', 'sort_order']
    list_editable = ['is_active', 'sort_order']
    list_filter = ['is_active']
    ordering = ['sort_order', 'id']


@admin.register(CustomerProfile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone', 'city']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'full_name', 'total_price', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    inlines = [OrderItemInline]