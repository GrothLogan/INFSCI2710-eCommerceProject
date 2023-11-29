import csv, json
from .models import *
from django.shortcuts import render
import random
from django.db import connection
from .forms import *
from django.http import HttpResponseRedirect
from django.views.generic import TemplateView, ListView, View
from django.http import (
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseServerError,
    JsonResponse
)
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib import messages
from django.http import (
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseServerError,
    JsonResponse
)
from django.contrib.auth import update_session_auth_hash
from django.db.models import Q
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models import Sum, Count
from .models import Product, Transaction, TransactionItem, Salesperson, Store, Region
from .forms import *
from datetime import datetime
from settings import STRIPE_PUBLIC_KEY

# Index View
def index(request):
    top_products = Product.objects.all()
    top_products = top_products.annotate(amount_purchased = Sum("inventory_items__order_items__quantity"))
    top_products = top_products.order_by("-amount_purchased")
    top_products = top_products[:6]
    return render(request, 'index.html',{'top_products': top_products})

# About View
def about(request):
    return render(request, 'about.html')

# Registration View
def register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('index')
    else:
        form = RegistrationForm()
    return render(request, 'register.html', {'form': form})

# Login View
def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('index')
        else:
            # Optionally, add an error message
            pass
    return render(request, 'login.html')

# Logout View
def logout_view(request):
    logout(request)
    return redirect('login')

# Profile View
@login_required
def profile(request):
    return render(request, 'profile.html', {'user': request.user})

# quick comment search and search results are new so dont delete them while you are merging are stuff Quinn
def search(request):
    if request.method == 'POST':
        form = SearchForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data["name"]
            description = form.cleaned_data["description"]
            category = form.cleaned_data["category"]
            seller = form.cleaned_data["seller"]
            min_rating = form.cleaned_data["min_rating"]
            available = form.cleaned_data["available"]
            min = form.cleaned_data["min_price"]
            max = form.cleaned_data["max_price"]
            # You may be wondering why i did this I bult a query string instead of just using django well the project requires sql and this is sql
            #products = Product.objects.all()
            query = "Select * from app_product Where name like '%%" + name + "%%' and description like '%%" + description + "%%' and listed = True" 
            #if name:
            #    products = products.filter(name__icontains = name)
            #if description:
            #    products = products.filter(description__icontains = description)
            if category:
                query = query + " and category_id = " + str(category.pk)
                #products = products.filter(category = category)
            if seller:
                query = query + " and store_id = " + str(seller.pk)
            products2 = Product.objects.raw(query)
            if min_rating:
                ids_above_rating = [product.id for product in products2 if product.avg_rating() >= min_rating]
                if len(ids_above_rating) > 0:
                    query = query + " and id in ("
                    for id in ids_above_rating:
                        query = query + str(id) + ","
                    query = query[:len(query)-1]
                    query = query +")"
                else:
                    query = query + " and FALSE "
                #products = products.filter(id__in = ids_above_rating)
            products2 = Product.objects.raw(query)
            if not available:
                ids_above_total_stock= [product.id for product in products2 if product.total_stock() > 0]
                if len(ids_above_total_stock) > 0:
                    query = query + " and id in ("
                    for id in ids_above_total_stock:
                        query = query + str(id) + ","
                    query = query[:len(query)-1]
                    query = query +")"
                else:
                    query = query + " and FALSE "
                #products = products.filter( stock__gt  = 0)
            if min:
                query = query + " and price >= " + str(min)
                #products = products.filter( price__gt  = min)
            if max:
                query = query + " and price <= " + str(max)
                #products = products.filter( price__lt  = max)
            products2 = Product.objects.raw(query)
            return render(request,'search_results.html', {'products_list': products2} )
            
                
    else:
        form = SearchForm()
    return render(request, 'search.html', {'form': form})

def update_profile(request):
    user = request.user
    if (user.is_authenticated):
        if(user.has_perm("app.associate")):
            salesperson = Salesperson.objects.get(pk = user.id)
            if request.method == 'POST':
                form = updateSalesperson(request.POST, instance = salesperson)
                if form.is_valid():
                    form.save()
            form2 = updateSalesperson(instance = salesperson)
            return render (request, "account.html", {'form': form2})
        else:
            customer = Customer.objects.get(pk = user.id)
            if request.method == 'POST':
                form = updateCustomer(request.POST, instance = customer)
                if form.is_valid():
                    form.save()
            if customer.kind == "Home":
                form2 = updateCustomer(instance = customer)
            else: 
                form2 = updateCompany(instance = customer)
            return render (request, "account.html", {'form': form2})
        
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Important!
            messages.success(request, 'Your password was successfully updated!')
            return redirect('update_profile')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'change_password.html', {
        'form': form
    })

def delete_profile(request):
    user = request.user
    if (user.is_authenticated):
        user.delete()
        return redirect("/")

def remove_from_cart(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    cart = request.session.get('cart', {})
    product_id_str = str(product_id)
    if product_id_str in cart:
        del cart[product_id_str]
        request.session['cart'] = cart
        request.session.modified = True
    return redirect('cart')


# Payment and Shipping
@login_required
def payment(request):
    user = request.user
    try:
        transaction = Transaction.objects.get(customer__user=user, status='Pending')  # Assuming each user has one pending transaction at a time
    except Transaction.DoesNotExist:
        # Handle the case where no transaction exists
        return redirect('cart')  # Redirect to cart if no pending transaction

    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            card_number = form.cleaned_data['card_number']
            expiration_date = form.cleaned_data['expiration_date']
            cvv = form.cleaned_data['cvv']
            
            # Assume a function process_payment which contacts a payment gateway and returns a boolean indicating success
            payment_success = process_payment(card_number, expiration_date, cvv, transaction.total_price)
            
            if payment_success:
                transaction.status = 'Processing'  # Change to 'Processing' upon successful payment
                transaction.save()
                return redirect('checkout')  # Redirect to checkout on successful payment
            else:
                form.add_error(None, 'Payment processing failed. Please try again.')  # Add a non-field error to the form
    else:
        form = PaymentForm()

    return render(request, 'payment.html', {'form': form})

@login_required
def shipping(request):
    try:
        # Assuming there's a transaction in progress for the logged-in user
        transaction = Transaction.objects.filter(customer=request.user.customer, status='Pending').latest('date')
    except Transaction.DoesNotExist:
        # Handle the case where there is no transaction in progress
        return redirect('cart')  # Or wherever you want to redirect

    if request.method == 'POST':
        form = ShippingForm(request.POST)
        if form.is_valid():
            # Save shipping information to the transaction
            transaction.shipping_address = form.cleaned_data['shipping_address']
            transaction.city = form.cleaned_data['city']
            transaction.state = form.cleaned_data['state']
            transaction.zip_code = form.cleaned_data['zip_code']
            transaction.save()  # Save the updated transaction object

            # Optionally update the order status
            transaction.status = 'Processing'
            transaction.save()

            return redirect('checkout')
    else:
        # Pre-fill the form with existing shipping info if available
        form = ShippingForm(initial={
            'shipping_address': transaction.shipping_address,
            'city': transaction.city,
            'state': transaction.state,
            'zip_code': transaction.zip_code,
        })

    return render(request, 'shipping.html', {'form': form})

# Salesperson Interface
@login_required
def sales_dashboard(request):
    try:
        # Assuming the logged in user has an associated Salesperson record
        salesperson = Salesperson.objects.get(email=request.user.email)
    except Salesperson.DoesNotExist:
        # Handle the case where the salesperson does not exist
        # This might redirect to a different page or show an error message
        return render(request, 'error.html', {'error_message': 'Salesperson not found'})

    # Fetch transactions associated with the salesperson
    transactions = Transaction.objects.filter(salesperson=salesperson)

    # Calculate total sales for the dashboard
    total_sales = sum(transaction.total_price for transaction in transactions if transaction.total_price)

    context = {
        'salesperson': salesperson,
        'transactions': transactions,
        'total_sales': total_sales,
    }

    return render(request, 'sales_dashboard.html', context)

# Store and Inventory Management
@login_required
def inventory(request):
    products = Product.objects.all()
    return render(request, 'inventory.html', {'products': products})

@login_required
def update_inventory(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    if request.method == 'POST':
        form = UpdateInventoryForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            return redirect('inventory')
    else:
        form = UpdateInventoryForm(instance=product)
    return render(request, 'update_inventory.html', {'form': form})

# Check if user is an admin
def admin_check(user):
    return user.is_staff


# Administrative Interface
@login_required
@user_passes_test(admin_check)
def admin_dashboard(request):
    # Assuming some basic stats for the dashboard
    total_sales = Transaction.objects.aggregate(Sum('total_price'))['total_price__sum']
    total_products = Product.objects.count()
    total_users = User.objects.count()
    return render(request, 'admin/admin_dashboard.html', {
        'total_sales': total_sales,
        'total_products': total_products,
        'total_users': total_users,
    })

@login_required
@user_passes_test(admin_check)
def manage_users(request):
    users = User.objects.all()
    return render(request, 'admin/manage_users.html', {'users': users})

@login_required
@user_passes_test(admin_check)
def manage_products(request):
    products = Product.objects.all()
    return render(request, 'admin/manage_products.html', {'products': products})

def test_ajax(request):
    if request.method == 'POST':
        return HttpResponse("This is a simple test message from test_ajax.")
    else:
        return HttpResponseForbidden("Invalid method.")    

# Helper objects and functions for AJAX functionality
switch = {
    'test_ajax': {'call': test_ajax},
}

def new_user(request):
    ## disallow dupe emails and make the input fields only accept valid input
    if request.method == "POST":
        form = newUser(request.POST)

        if form.is_valid():
            temp= form.save(commit=False)
            temp.kind ="Home"
            temp.save()
            return HttpResponseRedirect("/")
    # if a GET (or any other method) we'll create a blank form
    else:
        form = newUser()

    return render(request, "new_user.html", {"form": form})

def new_company(request):
    ## disallow dupe emails and make the input fields only accept valid input
    if request.method == "POST":
        form = newCompany(request.POST)
        if form.is_valid():
            temp= form.save(commit=False)
            temp.kind ="Business"
            temp.save()
            return HttpResponseRedirect("/")
    # if a GET (or any other method) we'll create a blank form
    else:
        form = newCompany()

    return render(request, "new_user.html", {"form": form})

def new_employee(request):
    user = request.user
    if user.has_perm("app.manager"):
        if request.method == "POST":
            form = newAssociate(request.POST)
            if form.is_valid():
                temp= form.save(commit=False)
                temp.kind ="Associate"
                temp.save()
                associate_perm = Permission.objects.get(codename="associate")
                
                manager_perm = Permission.objects.get(codename="manager")
                temp.user_permissions.add(associate_perm)
                if temp.kind == "Manager":
                    temp.user_permissions.add(manager_perm)
                temp.save()
                return HttpResponseRedirect("/")
        # if a GET (or any other method) we'll create a blank form
        else:
            form = newAssociate()

        return render(request, "new_user.html", {"form": form})
def new_manager(request):
    user = request.user
    if user.has_perm("app.region_manager"):
        if request.method == "POST":
            form = newManager(request.POST)
            if form.is_valid():
                temp= form.save(commit=False)
                temp.kind ="Manager"
                temp.save()
                associate_perm = Permission.objects.get(codename="associate")
                
                manager_perm = Permission.objects.get(codename="manager")
                temp.user_permissions.add(associate_perm)
                if temp.kind == "Manager":
                    temp.user_permissions.add(manager_perm)
                temp.save()
                return HttpResponseRedirect("/")
        # if a GET (or any other method) we'll create a blank form
        else:
            form = newManager()

        return render(request, "new_user.html", {"form": form})
    
def product_list(request):
    products = Product.objects.filter(listed = True)
    return render(request, 'product_list.html', {'products_list': products})
    
def categories(request):
    category = Category.objects.all()
    return render(request, "categories.html", {"category_list":category})

def category_products(request, category_id):
    products = Product.objects.filter(category= category_id) 
    products.filter(listed = True)
    category_name = Category.objects.get(id = category_id)
    return render(request, "category_product_list.html", {"category_name":category_name, "products_list":products})

def cart(request):
    ## add ability to edit amount in order.
    ## possible change this to transactions
    user = request.user
    if(user.is_authenticated):
        customer = Customer.objects.get(id = user.id)
        if request.method == "POST":
            form = cartForm(request.POST)
            if form.is_valid():

                changed_item = CartItem.objects.get(pk = form.cleaned_data["product_id"])
                changed_item.quantity = form.cleaned_data["quantity"]
                if form.cleaned_data["quantity"] > 0:
                    changed_item.save()
                else:
                    delete_cart(request,form.cleaned_data["product_id"])
        cart_list = CartItem.objects.filter(customer = customer.pk)
        total = 0
        flag = True
        for item in cart_list:
            item.subtotal  =(item.quantity * item.inventory.product.price)
            total = total + (item.quantity * item.inventory.product.price)
            if(item.quantity > item.inventory.quantity):
                flag = False
        return render(request, "cart.html", {"user":user, "cart_list":cart_list, "total":total, "flag":flag})
    else:
        return login

def empty_cart(request):
    user = request.user
    if(user.is_authenticated):
        ## it does reach here
        customer = Customer.objects.get(id = user.id)
        CartItem.objects.filter(customer = customer.pk).delete()
    return HttpResponseRedirect("/cart")

def delete_cart(request, cart_item_id):
    user = request.user
    if(user.is_authenticated):
        customer = Customer.objects.get(id = user.id)
        cart_list = CartItem.objects.filter(customer = customer.pk).filter(id = cart_item_id)
        cart_list.delete()
    return HttpResponseRedirect("/cart")

def product_page(request, product_id):
    ## add check for if user already has item in cart and let them edit
   
    user = request.user
    product = Product.objects.get(id = product_id)
    inventory_list = Inventory.objects.filter(product = product)
    review_list = Review.objects.filter(product= product)

    # Create a form with a dropdown for inventory selection
    inventory_choices = [(inv.id, f"{inv.store.address} - {inv.quantity} in stock") for inv in inventory_list]
    class InventoryForm(forms.Form):
        inventory = forms.ChoiceField(choices=inventory_choices, label="Select Store")
        quantity = forms.IntegerField(initial=1, min_value=1)
    
    inventory_form = InventoryForm()

    if(user.is_authenticated):
        customer = Customer.objects.get(id = user.id)
        inv_list = Inventory.objects.filter(product = product)
        cart = CartItem.objects.filter(customer =customer.pk).filter(inventory__in = inv_list)
        default_quant = 0
        flag = False
        if len(cart) > 0:
            default_quant = cart[0].quantity
            my_cart = cart[0]
            flag = True
        if request.method == "POST": 
            # Initialize form with POST data for POST requests
            inventory_form = InventoryForm(request.POST)

            form = confirmAdd(request.POST )
            if form.is_valid():
                temp_form = form.save(commit=False)
                if len(cart) > 0:
                    my_cart.quantity = temp_form.quantity
                    my_cart.save()
                    return HttpResponseRedirect("/")
                temp_form.customer = customer
                
                temp_form.save()
                return HttpResponseRedirect("/")
            form = reviewForm(request.POST)

            if form.is_valid():
                temp_form = form.save(commit=False)
                print(form.cleaned_data)
                review = Review.objects.filter(customer=customer.pk).filter(product = product_id)
                if len(review) > 0:
                    my_review = review[0]
                    my_review.rating = temp_form.rating
                    my_review.comment = temp_form.comment
                    my_review.save()
                else:
                    temp_form.product = product
                    temp_form.customer = customer
                    temp_form.save()
                review_list = Review.objects.filter(product= product)
        form_list = []
        for inv in inventory_list:
            new_form = addCart(inventory=inv.id,customer=user, initial={"quantity":default_quant})
            new_form.fields['inventory'].initial = inv
            field = new_form.fields['inventory']
            field.widget = forms.HiddenInput()
            form_list.append(new_form)
            
        review_form = reviewForm()
        return render(request, "product_page.html", {"inventory_form": inventory_form, "review_form": review_form, "product": product, "flag": flag, "reviews": review_list, "inventory": inventory_list})
    else:
        return render(request, "product_page.html", {"product":product, "reviews":review_list})

def checkout(request):
    # definitely need to add some safety checks
    user = request.user
    if(user.is_authenticated):
        customer = Customer.objects.get(id = user.id)
        checkout_cart = CartItem.objects.filter(customer = customer.pk)
        if(len(checkout_cart)<= 0):
            # should probably show an error message
            return HttpResponseRedirect("/")
        total = 0
        for item in checkout_cart:
            total = total + item.inventory.product.price * item.quantity
            if item.quantity > item.inventory.quantity:
                # again should probably lead to an error message
                return HttpResponseRedirect("/")
            
        if request.method == 'POST':

            form = CheckoutForm(request.POST)
            if form.is_valid():
                total = 0
                for item in checkout_cart:
                    total = total + (item.quantity * item.inventory.product.price)
                new_transaction = Transaction(customer = customer, total_price = total,
                                              date_ordered = datetime.utcnow,
                                                shipping_address = form.cleaned_data['shipping_address'] ,            
                                                city = form.cleaned_data['shipping_city'],
                                                state = form.cleaned_data['shipping_state'],
                                                zipcode = form.cleaned_data['shipping_zipcode'])
                salesperson = form.cleaned_data['assisting_salesperson_id']
                if salesperson:
                    new_transaction.salesperson = Salesperson.objects.get(username = salesperson)
                new_transaction.save()
                for item in checkout_cart:
                    subtotal = (item.quantity * item.inventory.product.price)
                    inventory = item.inventory
                    new_trans_item = TransactionItem(transaction = new_transaction, inventory = inventory, quantity = item.quantity, price = subtotal
 )
                    inventory.quantity = inventory.quantity - item.quantity
                    inventory.save()
                    new_trans_item.save()
                CartItem.objects.filter(customer = customer.pk).delete()
                return HttpResponseRedirect("/")
        else:
            form = CheckoutForm()
        return render(request, 'checkout.html', {'form': form, 'cart_list':checkout_cart, 'total':total})
    else:
        return HttpResponseRedirect("/")

def transaction_history(request):
    
    user = request.user
    if(user.is_authenticated):
        customer = Customer.objects.get(id = request.user.id)

        if(user.is_staff):
            transactions = Transaction.objects.filter()  
            # transactions = TransactionItem.objects.filter()   
        elif user.has_perm("app.region_manager"):
            salesperson = Salesperson.objects.get(pk = customer.pk)
            # transactions = TransactionItem.objects.filter(product__store__region = salesperson.store.region)
            transactions = Transaction.objects.filter()  
        elif user.has_perm("app.associate"):
            salesperson = Salesperson.objects.get(pk = customer.pk)
            transactions = Transaction.objects.filter(store = salesperson.store)
            # transactions = TransactionItem.objects.filter(product__store__id = salesperson.store.id)
        else:
            # transactions = TransactionItem.objects.filter(transaction__customer=customer)
            transactions = Transaction.objects.filter(customer=customer)
            
        transactions = transactions.order_by('-pk')
        return render(request, 'transaction_history.html', {'transactions': transactions})
    else:
        return redirect('login')
    
def transaction_history_customer(request,customer_id):
    user = request.user
    if(user.is_authenticated):
        salesperson = Salesperson.objects.get(id = request.user.id)
        flag = False
        
        if(user.is_staff):
            transactions = TransactionItem.objects.filter()  
            flag = True 
        elif user.has_perm("app.region_manager"):
            transactions = TransactionItem.objects.filter(product__store__region = salesperson.store.region)
            flag = True
        elif user.has_perm("app.associate"):
            transactions = TransactionItem.objects.filter(product__store__id = salesperson.store.id)
            flag = True
        if flag:
            transactions = transactions.filter(customer__id = customer_id)
            transactions = transactions.order_by('-pk')
            return render(request, 'transaction_history.html', {'transactions': transactions})
        else:
             return redirect('login')
    return redirect('login')
    
@login_required
def payment(request):
    user = request.user
    try:
        transaction = Transaction.objects.get(customer__user=user, status='Pending')  # Assuming each user has one pending transaction at a time
    except Transaction.DoesNotExist:
        # Handle the case where no transaction exists
        return redirect('cart')  # Redirect to cart if no pending transaction

    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            card_number = form.cleaned_data['card_number']
            expiration_date = form.cleaned_data['expiration_date']
            cvv = form.cleaned_data['cvv']
            
            # Assume a function process_payment which contacts a payment gateway and returns a boolean indicating success
            # payment_success = process_payment(card_number, expiration_date, cvv, transaction.total_price)
            payment_success = True
            if payment_success:
                transaction.status = 'Processing'  # Change to 'Processing' upon successful payment
                transaction.save()
                return redirect('checkout')  # Redirect to checkout on successful payment
            else:
                form.add_error(None, 'Payment processing failed. Please try again.')  # Add a non-field error to the form
    else:
        form = PaymentForm()

    return render(request, 'payment.html', {'form': form})

@login_required
def shipping(request):
    try:
        # Assuming there's a transaction in progress for the logged-in user
        transaction = Transaction.objects.filter(customer=request.user.customer, status='Pending').latest('date')
    except Transaction.DoesNotExist:
        # Handle the case where there is no transaction in progress
        return redirect('cart')  # Or wherever you want to redirect

    if request.method == 'POST':
        form = ShippingForm(request.POST)
        if form.is_valid():
            # Save shipping information to the transaction
            transaction.shipping_address = form.cleaned_data['shipping_address']
            transaction.city = form.cleaned_data['city']
            transaction.state = form.cleaned_data['state']
            transaction.zip_code = form.cleaned_data['zip_code']
            transaction.save()  # Save the updated transaction object

            # Optionally update the order status
            transaction.status = 'Processing'
            transaction.save()

            return redirect('checkout')
    else:
        # Pre-fill the form with existing shipping info if available
        form = ShippingForm(initial={
            'shipping_address': transaction.shipping_address,
            'city': transaction.city,
            'state': transaction.state,
            'zip_code': transaction.zip_code,
        })

    return render(request, 'shipping.html', {'form': form})


# Aggregations and stuff
def sales_report(request):
    user = request.user
    if user.has_perm("app.associate"):
        products = Product.objects.all()
        
        return render(request, 'report_sales.html', {'products':products})

def category_report(request):
    user = request.user
    if user.has_perm("app.associate"):
        categories = Category.objects.all()
        return render(request, 'category_report.html', {'categories':categories})
def region_report(request):
    user = request.user
    if user.has_perm("app.associate"):
        regions = Region.objects.all()
        return render(request, 'report_region.html', {'regions':regions})
def salesperson_report(request):
    user = request.user
    if user.has_perm("app.associate"):
        salespeople = Salesperson.objects.all()
        return render(request, 'report_salesperson.html', {'salespeople':salespeople})
    
    
def business_product_report_search(request):
    user = request.user
    if user.has_perm("app.associate"):
        if request.method == 'POST':
            form = SearchForm(request.POST)
            if form.is_valid():
                name = form.cleaned_data["name"]
                description = form.cleaned_data["description"]
                category = form.cleaned_data["category"]
                seller = form.cleaned_data["seller"]
                min_rating = form.cleaned_data["min_rating"]
                available = form.cleaned_data["available"]
                min = form.cleaned_data["min_price"]
                max = form.cleaned_data["max_price"]
                # You may be wondering why i did this I bult a query string instead of just using django well the project requires sql and this is sql
                #products = Product.objects.all()
                query = "Select * from app_product Where name like '%%" + name + "%%' and description like '%%" + description + "%%' and listed = True" 
                #if name:
                #    products = products.filter(name__icontains = name)
                #if description:
                #    products = products.filter(description__icontains = description)
                if category:
                    query = query + " and category_id = " + str(category.pk)
                    #products = products.filter(category = category)
                if seller:
                    query = query + " and store_id = " + str(seller.pk)
                products2 = Product.objects.raw(query)
                if min_rating:
                    ids_above_rating = [product.id for product in products2 if product.avg_rating() >= min_rating]
                    if len(ids_above_rating) > 0:
                        query = query + " and id in ("
                        for id in ids_above_rating:
                            query = query + str(id) + ","
                        query = query[:len(query)-1]
                        query = query +")"
                    else:
                        query = query + " and FALSE "
                    #products = products.filter(id__in = ids_above_rating)
                products2 = Product.objects.raw(query)
                if not available:
                    ids_above_total_stock= [product.id for product in products2 if product.total_stock() > 0]
                    if len(ids_above_total_stock) > 0:
                        query = query + " and id in ("
                        for id in ids_above_total_stock:
                            query = query + str(id) + ","
                        query = query[:len(query)-1]
                        query = query +")"
                    else:
                        query = query + " and FALSE "
                    #products = products.filter( stock__gt  = 0)
                if min:
                    query = query + " and price >= " + str(min)
                    #products = products.filter( price__gt  = min)
                if max:
                    query = query + " and price <= " + str(max)
                    #products = products.filter( price__lt  = max)
                products2 = Product.objects.raw(query)
                return render(request,'search_report_results.html', {'products_list': products2} )
        else:
            form = SearchForm()
        return render(request, 'search.html', {'form': form})
        
def business_product_report(request, product_id):
    user = request.user
    if user.has_perm("app.associate"):
        product = Product.objects.get(pk = product_id)
        businesses = Customer.objects.filter(kind="Business")
        anno_businesses = businesses.annotate(amount_purchased = Sum("customer_transactions__transaction__quantity"), filter = Q(customer_transactions__transaction__inventory__product__id = product_id))
        return render(request, 'report_business_product.html', {'businesses':anno_businesses, "product":product})
        
# managment stuffs

def store_list(request):
    user = request.user
    if user.has_perm("app.region_manager"):
        if(user.is_staff):
            stores_list = Store.objects.filter()
        else:
            salesperson = Salesperson.objects.get(pk = user.id)
            stores_list = Store.objects.filter(region = salesperson.store.region)
        return render(request, 'store_list.html', {'stores_list':stores_list})

def store_redirect(request):
    user = request.user
    if user.has_perm("app.manager"):
        salesperson = Salesperson.objects.get(pk = user.id)
        return redirect("store_page", store_id = salesperson.store.pk)
    
def store_page(request, store_id):
    user = request.user
    if user.has_perm("app.associate"):
        
        if request.method == "POST":
            form = storeForm(request.POST)
            if form.is_valid():
                changed_item = Inventory.objects.get(pk = form.cleaned_data["product_id"])
                changed_item.quantity = form.cleaned_data["quantity"]
                changed_item.save()

        store= Store.objects.get(id = store_id)
        inventories = Inventory.objects.filter(store__id = store_id)
        return render(request, 'store.html', {'store':store, 'inventories':inventories})
    
def add_inventory(request, store_id):
    user = request.user
    if user.has_perm("app.manager"):
        if request.method == "POST":
            form = newInventory(request.POST)
            if form.is_valid():
                temp = form.save(commit=False)
                
                temp.store = Store.objects.get(id = store_id)
                inventories = Inventory.objects.filter(store = temp.store ).filter(product=temp.product)
                if len(inventories) > 0:
                    inv = Inventory.objects.filter(store = temp.store ).get(product=temp.product)
                    inv.quantity = inv.quantity + temp.quantity
                    inv.save()
                else:
                    temp.save()
                return redirect(store_page, store_id=store_id)
        else:
            form = newInventory()
        return render (request, "add_inventory.html", {"form":form})
def delete_store(request, store_id):
    user = request.user
    if user.has_perm("app.region_manager"):
        store = Store.objects.get(id = store_id)
        store.delete()
    return redirect(store_list)
def delete_inventory(request, inventory_id):
    user = request.user
    if user.has_perm("app.manager"):
        inventory = Inventory.objects.get(id = inventory_id)
        store_id = inventory.store.id
        inventory.delete()
        return redirect(store_page, store_id=store_id )
    return redirect("/")
def delete_product(request, product_id):
    user = request.user
    if user.has_perm("app.region_manager"):
        product = Product.objects.get(id = product_id)
        product.delete()
    return redirect("/")
def new_product(request):
    user = request.user
    if user.has_perm("app.region_manager"):    
        if request.method == "POST":
            form = newProduct(request.POST)
            if form.is_valid():
                form.save()
            return redirect("/")
        else:
            form = newProduct()
        return render(request, "new_product.html", {"form":form})

# Helper objects and functions for AJAX functionality
switch = {
    'test_ajax': {'call': test_ajax},
}

def ajax(request):
    """Switch to correct function given POST call

    Receives the following from POST:
    call -- What function to redirect to
    """
    post_call = request.POST.get('call', '')

    # Abort if there is no valid call sent to us from Javascript
    if not post_call:
        return HttpResponseServerError()

    # Route the request to the correct handler function
    # and pass request to the functions
    try:
        # select the function from the dictionary
        selection = switch[post_call]
    # If all else fails, handle the error message
    except KeyError:
        return HttpResponseServerError()

    else:
        procedure = selection.get('call')
        validation = selection.get('validation', None)
        if validation:
            valid = validation(request)

            if not valid:
                return HttpResponseForbidden()

        # execute the function
        return procedure(request)


# QKW - Stripe Views
class StripePayment(View):
    def get(self, request, *args, **kwargs):
        context = {
            'stripe_public_key': STRIPE_PUBLIC_KEY
        }
        return render(request, 'stripe_payment.html', context)


class StripeSuccess(View):
    def get(self, request, *args, **kwargs):
        # Gotta put successful payment stuff here!
        # e.g., updating order status, sending confirmation email, etc.
        # Create the subscription model, then figure this out.
        # TODO Do we register the subscription with Stripe and register a cancellation later?
        # TODO Or do we do a single payment and handle periodicity on our end?
        return render(request, 'stripe_success.html')


class StripeCancel(View):
    def get(self, request, *args, **kwargs):
        # TODO I need to read more into cancellations, rejections, etc. etc.
        return render(request, 'stripe_cancel.html')