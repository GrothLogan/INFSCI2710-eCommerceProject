# Generated by Django 4.2.7 on 2023-11-03 16:28

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0004_remove_cartitem_cart_cartitem_customer'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Order',
            new_name='Transaction',
        ),
        migrations.RenameModel(
            old_name='OrderItem',
            new_name='TransactionItem',
        ),
    ]
