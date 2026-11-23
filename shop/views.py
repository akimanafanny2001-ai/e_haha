from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from decimal import Decimal

from .models import Category, Product, Order, OrderItem, CustomerProfile
from .forms import RegisterForm, LoginForm, CheckoutForm, ProfileForm


def home(request):
    categories = Category.objects.all()
    featured_products = Product.objects.filter(is_available=True, is_featured=True)[:8]
    latest_products = Product.objects.filter(is_available=True)[:8]
    return render(request, 'shop/home.html', {
        'categories': categories,
        'featured_products': featured_products,
        'latest_products': latest_products,
    })


def product_list(request):
    category_slug = request.GET.get('category')
    search = request.GET.get('q', '')
    sort = request.GET.get('sort', '-created_at')

    products = Product.objects.filter(is_available=True)
    categories = Category.objects.all()
    active_category = None

    if category_slug:
        active_category = get_object_or_404(Category, slug=category_slug)
        products = products.filter(category=active_category)

    if search:
        products = products.filter(Q(name__icontains=search) | Q(description__icontains=search))

    allowed_sorts = {'price', '-price', 'name', '-name', '-created_at'}
    if sort in allowed_sorts:
        products = products.order_by(sort)

    return render(request, 'shop/product_list.html', {
        'products': products,
        'categories': categories,
        'active_category': active_category,
        'search': search,
        'sort': sort,
    })


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug)
    products = category.products.filter(is_available=True)
    return render(request, 'shop/category_detail.html', {
        'category': category,
        'products': products,
    })


def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, is_available=True)
    related = Product.objects.filter(category=product.category, is_available=True).exclude(id=product.id)[:4]
    return render(request, 'shop/product_detail.html', {
        'product': product,
        'related_products': related,
    })


# ---------- CART (session based) ----------
def _get_cart(request):
    cart = request.session.setdefault('cart', {})
    cleaned = {}
    for pid, qty in cart.items():
        try:
            pid_int = int(pid)
            qty_int = int(qty)
        except (TypeError, ValueError):
            continue
        if pid_int > 0 and qty_int > 0:
            cleaned[str(pid_int)] = qty_int
    if cleaned != cart:
        request.session['cart'] = cleaned
        request.session.modified = True
    elif 'cart' not in request.session:
        request.session['cart'] = cleaned
        request.session.modified = True
    else:
        request.session['cart'] = cleaned
    return cleaned


def _build_cart_items(cart):
    items = []
    total = Decimal('0.00')
    for pid, qty in cart.items():
        try:
            product = Product.objects.get(id=int(pid), is_available=True)
        except (Product.DoesNotExist, ValueError, TypeError):
            continue
        qty = min(qty, product.stock)
        if qty <= 0:
            continue
        subtotal = product.price * qty
        total += subtotal
        items.append({'product': product, 'qty': qty, 'subtotal': subtotal})
    return items, total


def cart_view(request):
    cart = _get_cart(request)
    items, total = _build_cart_items(cart)
    valid_cart = {str(it['product'].id): it['qty'] for it in items}
    if valid_cart != cart:
        request.session['cart'] = valid_cart
        request.session.modified = True
    return render(request, 'shop/cart.html', {'items': items, 'total': total})

@require_POST
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_available=True)
    if product.stock <= 0:
        messages.error(request, f"'{product.name}' is currently out of stock.")
        return redirect(request.META.get('HTTP_REFERER') or product.get_absolute_url())
    try:
        qty = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        qty = 0
    if qty < 1:
        messages.error(request, 'Please choose a valid quantity.')
        return redirect(product.get_absolute_url())
    cart = _get_cart(request)
    pid = str(product.id)
    new_qty = cart.get(pid, 0) + qty
    if new_qty > product.stock:
        new_qty = product.stock
        messages.warning(request, f"Only {product.stock} {product.unit} of '{product.name}' is available.")
    cart[pid] = new_qty
    request.session.modified = True
    messages.success(request, f"Added '{product.name}' to cart.")
    return redirect(request.META.get('HTTP_REFERER', 'shop:product_list'))

@require_POST
def update_cart(request, product_id):
    cart = _get_cart(request)
    pid = str(product_id)
    try:
        qty = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        qty = 0
    if qty <= 0:
        cart.pop(pid, None)
    else:
        product = Product.objects.filter(id=product_id, is_available=True).first()
        if product:
            cart[pid] = min(qty, product.stock)
            if cart[pid] <= 0:
                cart.pop(pid, None)
        else:
            cart.pop(pid, None)
    request.session.modified = True
    return redirect('shop:cart')

@require_POST
def remove_from_cart(request, product_id):
    cart = _get_cart(request)
    cart.pop(str(product_id), None)
    request.session.modified = True
    messages.info(request, 'Item removed from cart.')
    return redirect('shop:cart')


# ---------- CHECKOUT / ORDERS ----------
@login_required
def checkout(request):
    cart = _get_cart(request)
    if not cart:
        messages.warning(request, 'Your cart is empty.')
        return redirect('shop:product_list')

    items, total = _build_cart_items(cart)
    if not items:
        request.session['cart'] = {}
        request.session.modified = True
        messages.warning(request, 'Your cart no longer contains available products.')
        return redirect('shop:product_list')

    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                locked_products = {
                    p.id: p
                    for p in Product.objects.select_for_update().filter(
                        id__in=[it['product'].id for it in items],
                        is_available=True,
                    )
                }
                stock_error = None
                for it in items:
                    product = locked_products.get(it['product'].id)
                    if product is None or product.stock < it['qty']:
                        stock_error = it['product'].name
                        break

                if stock_error:
                    messages.error(
                        request,
                        f"'{stock_error}' does not have enough stock. Please update your cart.",
                    )
                    return redirect('shop:cart')

                order = form.save(commit=False)
                order.user = request.user
                order.total_price = sum(
                    (it['product'].price * it['qty'] for it in items),
                    Decimal('0.00'),
                )
                order.save()
                for it in items:
                    product = locked_products[it['product'].id]
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        price=product.price,
                        quantity=it['qty'],
                    )
                    product.stock -= it['qty']
                    product.save(update_fields=['stock', 'updated_at'])
            request.session['cart'] = {}
            request.session.modified = True
            messages.success(request, f'Order #{order.id} placed successfully!')
            return redirect('shop:order_success', order_id=order.id)
    else:
        initial = {'full_name': request.user.get_full_name() or request.user.username, 'phone': ''}
        try:
            prof = request.user.profile
            initial.update({'phone': prof.phone, 'address': prof.address, 'city': prof.city})
        except CustomerProfile.DoesNotExist:
            pass
        form = CheckoutForm(initial=initial)

    return render(request, 'shop/checkout.html', {'form': form, 'items': items, 'total': total})


@login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'shop/order_success.html', {'order': order})


@login_required
def my_orders(request):
    orders = Order.objects.filter(user=request.user)
    return render(request, 'shop/my_orders.html', {'orders': orders})


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'shop/order_detail.html', {'order': order})


# ---------- ACCOUNTS ----------
def register_view(request):
    if request.user.is_authenticated:
        return redirect('shop:home')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome, {user.username}!')
            return redirect('shop:home')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('shop:home')
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password']
            )
            if user:
                login(request, user)
                messages.success(request, 'Logged in successfully.')
                next_url = request.GET.get('next')
                if next_url and url_has_allowed_host_and_scheme(
                    next_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    return redirect(next_url)
                return redirect('shop:home')
            messages.error(request, 'Invalid credentials.')
    else:
        form = LoginForm()
    return render(request, 'accounts/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, 'Logged out.')
    return redirect('shop:home')


@login_required
def profile_view(request):
    profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('shop:profile')
    else:
        form = ProfileForm(instance=profile)
    return render(request, 'accounts/profile.html', {'form': form, 'profile': profile})