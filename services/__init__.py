import pandas as pd
from sqlalchemy import func

from database.connection import SessionLocal
from database.models import Product, Sale, SaleItem


def get_dashboard_metrics():
    with SessionLocal() as session:
        total_products = session.query(func.count(Product.id)).scalar() or 0

        total_revenue = session.query(
            func.coalesce(func.sum(Sale.total_amount), 0)
        ).scalar()

        inventory_value = session.query(
            func.coalesce(
                func.sum(Product.purchase_price * Product.quantity), 0
            )
        ).scalar()

        low_stock_count = session.query(
            func.count(Product.id)
        ).filter(
            Product.quantity <= Product.minimum_stock
        ).scalar() or 0

        return {
            'total_products': total_products,
            'total_revenue': float(total_revenue),
            'inventory_value': float(inventory_value),
            'low_stock_count': low_stock_count
        }


def get_sales_chart_data():
    with SessionLocal() as session:
        results = session.query(
            func.date(Sale.created_at).label('sale_date'),
            func.sum(Sale.total_amount).label('revenue')
        ).group_by(
            func.date(Sale.created_at)
        ).order_by(
            func.date(Sale.created_at)
        ).all()

        return pd.DataFrame(
            results,
            columns=['Date', 'Revenue']
        )


def get_low_stock_products():
    with SessionLocal() as session:
        products = session.query(Product).filter(
            Product.quantity <= Product.minimum_stock
        ).order_by(Product.quantity).all()

        return [
            {
                'SKU': product.sku,
                'Product': product.name,
                'Stock': product.quantity,
                'Minimum Stock': product.minimum_stock
            }
            for product in products
        ]


def get_recent_sales(limit=5):
    with SessionLocal() as session:
        sales = session.query(Sale).order_by(
            Sale.created_at.desc()
        ).limit(limit).all()

        return [
            {
                'Invoice': sale.invoice_number,
                'Date': sale.created_at.strftime('%d %b %Y, %H:%M'),
                'Total (₹)': round(sale.total_amount, 2)
            }
            for sale in sales
        ]


def get_best_selling_products(limit=5):
    with SessionLocal() as session:
        results = session.query(
            Product.name,
            func.sum(SaleItem.quantity).label('units_sold')
        ).join(
            SaleItem, SaleItem.product_id == Product.id
        ).group_by(
            Product.id, Product.name
        ).order_by(
            func.sum(SaleItem.quantity).desc()
        ).limit(limit).all()

        return pd.DataFrame(
            results,
            columns=['Product', 'Units Sold']
        )