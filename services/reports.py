
import pandas as pd

from sqlalchemy import func

from database.connection import SessionLocal
from database.models import Product, Sale, SaleItem


# --------------------------------------------------
# SALES REPORT
# --------------------------------------------------

def get_sales_report(start_date, end_date):
    """Return invoices created within the selected date range."""

    with SessionLocal() as session:
        sales = (
            session.query(
                Sale.id.label('sale_id'),
                Sale.invoice_number.label('invoice_number'),
                Sale.total_amount.label('total_amount'),
                Sale.created_at.label('created_at')
            )
            .filter(
                Sale.created_at >= start_date,
                Sale.created_at < end_date
            )
            .order_by(Sale.created_at.desc())
            .all()
        )

    return pd.DataFrame(
        [dict(row._mapping) for row in sales],
        columns=[
            'sale_id',
            'invoice_number',
            'total_amount',
            'created_at'
        ]
    )


# --------------------------------------------------
# PRODUCT SALES REPORT
# --------------------------------------------------

def get_product_sales_report(start_date, end_date):
    """Return product-level sales and estimated gross profit."""

    with SessionLocal() as session:
        rows = (
            session.query(
                Product.id.label('product_id'),
                Product.name.label('product_name'),
                func.sum(SaleItem.quantity).label('quantity_sold'),
                func.sum(SaleItem.subtotal).label('total_revenue'),
                Product.purchase_price.label('purchase_price')
            )
            .join(SaleItem, SaleItem.product_id == Product.id)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .filter(
                Sale.created_at >= start_date,
                Sale.created_at < end_date
            )
            .group_by(
                Product.id,
                Product.name,
                Product.purchase_price
            )
            .order_by(func.sum(SaleItem.quantity).desc())
            .all()
        )

    columns = [
        'product_id',
        'product_name',
        'quantity_sold',
        'total_revenue',
        'purchase_price'
    ]

    df = pd.DataFrame(
        [dict(row._mapping) for row in rows],
        columns=columns
    )

    if not df.empty:
        df['quantity_sold'] = pd.to_numeric(
            df['quantity_sold'], errors='coerce'
        ).fillna(0)

        df['total_revenue'] = pd.to_numeric(
            df['total_revenue'], errors='coerce'
        ).fillna(0)

        df['purchase_price'] = pd.to_numeric(
            df['purchase_price'], errors='coerce'
        ).fillna(0)

        df['estimated_cost'] = (
            df['quantity_sold'] * df['purchase_price']
        )

        df['estimated_gross_profit'] = (
            df['total_revenue'] - df['estimated_cost']
        )

    return df


# --------------------------------------------------
# INVENTORY REPORT
# --------------------------------------------------

def get_inventory_report():
    """Return current product and inventory information."""

    with SessionLocal() as session:
        products = (
            session.query(
                Product.id.label('product_id'),
                Product.sku.label('sku'),
                Product.name.label('product_name'),
                Product.category.label('category'),
                Product.purchase_price.label('purchase_price'),
                Product.selling_price.label('selling_price'),
                Product.quantity.label('quantity'),
                Product.minimum_stock.label('minimum_stock')
            )
            .order_by(Product.name)
            .all()
        )

    columns = [
        'product_id',
        'sku',
        'product_name',
        'category',
        'purchase_price',
        'selling_price',
        'quantity',
        'minimum_stock'
    ]

    df = pd.DataFrame(
        [dict(row._mapping) for row in products],
        columns=columns
    )

    if not df.empty:
        df['inventory_cost_value'] = (
            df['purchase_price'] * df['quantity']
        )

        df['inventory_selling_value'] = (
            df['selling_price'] * df['quantity']
        )

        df['stock_status'] = df.apply(
            lambda row: (
                'Low Stock'
                if row['quantity'] <= row['minimum_stock']
                else 'In Stock'
            ),
            axis=1
        )

    return df


# --------------------------------------------------
# SALES SUMMARY
# --------------------------------------------------

def get_sales_summary(sales_df, product_sales_df):
    """Calculate sales metrics and always return a dictionary."""

    summary = {
        'total_revenue': 0.0,
        'invoice_count': 0,
        'total_units_sold': 0,
        'average_invoice_value': 0.0,
        'estimated_gross_profit': 0.0,
        'profit_margin': 0.0
    }

    # Safely handle missing report data.
    if sales_df is None:
        sales_df = pd.DataFrame()

    if product_sales_df is None:
        product_sales_df = pd.DataFrame()

    # Revenue and invoice metrics.
    if not sales_df.empty:
        if 'total_amount' in sales_df.columns:
            summary['total_revenue'] = float(
                pd.to_numeric(
                    sales_df['total_amount'],
                    errors='coerce'
                ).fillna(0).sum()
            )

        if 'invoice_number' in sales_df.columns:
            summary['invoice_count'] = int(
                sales_df['invoice_number'].nunique()
            )
        else:
            summary['invoice_count'] = len(sales_df)

        if summary['invoice_count'] > 0:
            summary['average_invoice_value'] = (
                summary['total_revenue']
                / summary['invoice_count']
            )

    # Product sales metrics.
    if not product_sales_df.empty:
        if 'quantity_sold' in product_sales_df.columns:
            summary['total_units_sold'] = int(
                pd.to_numeric(
                    product_sales_df['quantity_sold'],
                    errors='coerce'
                ).fillna(0).sum()
            )

        if 'estimated_gross_profit' in product_sales_df.columns:
            summary['estimated_gross_profit'] = float(
                pd.to_numeric(
                    product_sales_df['estimated_gross_profit'],
                    errors='coerce'
                ).fillna(0).sum()
            )

    # Calculate profit margin safely.
    if summary['total_revenue'] > 0:
        summary['profit_margin'] = (
            summary['estimated_gross_profit']
            / summary['total_revenue']
        ) * 100

    return summary