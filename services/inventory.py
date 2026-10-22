from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from database.connection import SessionLocal
from database.models import Product


def get_all_products(search=''):
    with SessionLocal() as session:
        query = session.query(Product)

        if search:
            search_term = f'%{search}%'

            query = query.filter(
                or_(
                    Product.name.ilike(search_term),
                    Product.sku.ilike(search_term),
                    Product.category.ilike(search_term)
                )
            )

        products = query.order_by(Product.name).all()

        return [
            {
                'id': product.id,
                'sku': product.sku,
                'name': product.name,
                'category': product.category,
                'purchase_price': product.purchase_price,
                'selling_price': product.selling_price,
                'quantity': product.quantity,
                'minimum_stock': product.minimum_stock,
                'created_at': product.created_at
            }
            for product in products
        ]


def add_product(
    sku,
    name,
    category,
    purchase_price,
    selling_price,
    quantity,
    minimum_stock
):
    with SessionLocal() as session:
        try:
            product = Product(
                sku=sku.strip(),
                name=name.strip(),
                category=category.strip(),
                purchase_price=purchase_price,
                selling_price=selling_price,
                quantity=quantity,
                minimum_stock=minimum_stock
            )

            session.add(product)
            session.commit()

            return True, 'Product added successfully!'

        except IntegrityError:
            session.rollback()
            return False, 'This SKU already exists or the product violates a database constraint.'

        except Exception:
            session.rollback()
            return False, 'Unable to add product. Please check the input and database connection.'


def update_product(
    product_id,
    sku,
    name,
    category,
    purchase_price,
    selling_price,
    quantity,
    minimum_stock
):
    with SessionLocal() as session:
        try:
            product = session.get(Product, product_id)

            if product is None:
                return False, 'Product not found.'

            product.sku = sku.strip()
            product.name = name.strip()
            product.category = category.strip()
            product.purchase_price = purchase_price
            product.selling_price = selling_price
            product.quantity = quantity
            product.minimum_stock = minimum_stock

            session.commit()

            return True, 'Product updated successfully!'

        except IntegrityError:
            session.rollback()
            return False, 'The SKU already exists or the product violates a database constraint.'

        except Exception:
            session.rollback()
            return False, 'Unable to update product. Please try again.'


def delete_product(product_id):
    with SessionLocal() as session:
        try:
            product = session.get(Product, product_id)

            if product is None:
                return False, 'Product not found.'

            if product.quantity != 0:
                return False, 'Only products with zero stock can be deleted.'

            session.delete(product)
            session.commit()

            return True, 'Product deleted successfully!'

        except IntegrityError:
            session.rollback()
            return False, 'This product has sales history and cannot be deleted.'

        except Exception:
            session.rollback()
            return False, 'Unable to delete product. Please try again.'