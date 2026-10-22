from datetime import datetime
from io import BytesIO
from uuid import uuid4

import pandas as pd
import streamlit as st
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from database.connection import SessionLocal
from database.models import Product, Sale, SaleItem
from services.billing import calculate_invoice


st.set_page_config(page_title="StockFlow | Billing", page_icon="🧾", layout="wide")
st.title("🧾 StockFlow Billing & Invoicing")
st.caption("Create invoices with GST, discounts, PDF receipts, and automatic stock updates.")


def create_invoice_pdf(sale_id: int) -> bytes:
    """Create a PDF using the saved invoice values."""
    buffer = BytesIO()

    with SessionLocal() as db:
        sale = db.get(Sale, sale_id)
        if sale is None:
            raise ValueError("Invoice not found.")

        rows = db.execute(
            select(SaleItem, Product.name, Product.sku)
            .join(Product, SaleItem.product_id == Product.id)
            .where(SaleItem.sale_id == sale_id)
        ).all()

        styles = getSampleStyleSheet()
        story = [
            Paragraph("StockFlow", styles["Title"]),
            Paragraph("Sales Invoice", styles["Heading2"]),
            Spacer(1, 6 * mm),
            Paragraph(f"Invoice: {sale.invoice_number}", styles["Normal"]),
            Paragraph(f"Date: {sale.created_at:%d-%m-%Y %H:%M}", styles["Normal"]),
            Spacer(1, 5 * mm),
        ]

        is_legacy = getattr(sale, "pricing_mode", "legacy") == "legacy"

        if is_legacy:
            table_data = [["Product", "SKU", "Qty", "Unit Price", "Subtotal"]]
            for item, name, sku in rows:
                table_data.append([
                    str(name), str(sku), str(item.quantity),
                    f"Rs. {item.unit_price:.2f}", f"Rs. {item.subtotal:.2f}",
                ])
        else:
            table_data = [[
                "Product", "SKU", "Qty", "Price", "GST %", "Discount",
                "Taxable", "GST", "Total",
            ]]
            for item, name, sku in rows:
                table_data.append([
                    str(name), str(sku), str(item.quantity),
                    f"{item.unit_price:.2f}", f"{item.gst_rate:.2f}%",
                    f"{item.discount_amount:.2f}", f"{item.taxable_amount:.2f}",
                    f"{item.gst_amount:.2f}", f"{item.total_amount:.2f}",
                ])

        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([table, Spacer(1, 6 * mm)])

        if not is_legacy:
            story.extend([
                Paragraph(f"Subtotal: Rs. {sale.subtotal:.2f}", styles["Normal"]),
                Paragraph(f"Discount: Rs. {sale.discount_amount:.2f}", styles["Normal"]),
                Paragraph(f"Taxable amount: Rs. {sale.taxable_amount:.2f}", styles["Normal"]),
                Paragraph(f"GST amount: Rs. {sale.gst_amount:.2f}", styles["Normal"]),
                Spacer(1, 3 * mm),
            ])

        story.append(
            Paragraph(f"<b>Invoice total: Rs. {sale.total_amount:.2f}</b>", styles["Heading2"])
        )

        document = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=12 * mm, leftMargin=12 * mm,
            topMargin=12 * mm, bottomMargin=12 * mm,
        )
        document.build(story)

    return buffer.getvalue()


def save_sale(cart, pricing_mode, discount_type, discount_value, gst_rates):
    """Validate stock, save invoice details, and deduct stock atomically."""
    if not cart:
        return False, "The invoice is empty.", None

    with SessionLocal() as db:
        try:
            product_ids = sorted(int(pid) for pid in cart)
            products = db.execute(
                select(Product)
                .where(Product.id.in_(product_ids))
                .order_by(Product.id)
                .with_for_update()
            ).scalars().all()
            products_by_id = {product.id: product for product in products}

            if len(products_by_id) != len(product_ids):
                return False, "One or more selected products no longer exist.", None

            calculation_items = []
            for product_id in product_ids:
                product = products_by_id[product_id]
                quantity = int(cart[product_id])

                if quantity <= 0:
                    return False, "Product quantity must be greater than zero.", None
                if product.quantity < quantity:
                    return (
                        False,
                        f"Insufficient stock for {product.name}. Available: {product.quantity}.",
                        None,
                    )

                gst_rate = float(gst_rates.get(product_id, product.gst_rate))
                if not 0 <= gst_rate <= 100:
                    return False, "GST rates must be between 0 and 100%.", None

                calculation_items.append({
                    "product_id": product.id,
                    "name": product.name,
                    "quantity": quantity,
                    "unit_price": float(product.selling_price),
                    "gst_rate": gst_rate,
                })

            invoice = calculate_invoice(
                items=calculation_items,
                pricing_mode=pricing_mode,
                discount_type=discount_type,
                discount_value=float(discount_value),
            )

            invoice_number = f"SF-{datetime.now():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"
            sale = Sale(
                invoice_number=invoice_number,
                subtotal=float(invoice["subtotal"]),
                discount_type=invoice["discount_type"],
                discount_value=float(invoice["discount_value"]),
                discount_amount=float(invoice["discount_amount"]),
                taxable_amount=float(invoice["taxable_amount"]),
                gst_amount=float(invoice["gst_amount"]),
                pricing_mode=invoice["pricing_mode"],
                total_amount=float(invoice["total_amount"]),
            )
            db.add(sale)
            db.flush()

            calculated_by_id = {
                int(item["product_id"]): item for item in invoice["items"]
            }

            for product_id in product_ids:
                product = products_by_id[product_id]
                line = calculated_by_id[product_id]
                quantity = int(cart[product_id])

                db.add(SaleItem(
                    sale_id=sale.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_price=float(product.selling_price),
                    subtotal=float(line["subtotal"]),
                    gst_rate=float(line["gst_rate"]),
                    discount_amount=float(line["discount_amount"]),
                    taxable_amount=float(line["taxable_amount"]),
                    gst_amount=float(line["gst_amount"]),
                    total_amount=float(line["total_amount"]),
                ))
                product.quantity -= quantity

            db.commit()
            return True, invoice_number, sale.id

        except (ValueError, TypeError, KeyError) as exc:
            db.rollback()
            return False, f"Invoice calculation error: {exc}", None
        except SQLAlchemyError:
            db.rollback()
            return False, "Database error. The invoice was not saved.", None


# Session state
if "stockflow_cart" not in st.session_state:
    st.session_state.stockflow_cart = {}
if "stockflow_gst_rates" not in st.session_state:
    st.session_state.stockflow_gst_rates = {}
if "stockflow_last_sale_id" not in st.session_state:
    st.session_state.stockflow_last_sale_id = None


# Load products
with SessionLocal() as db:
    products = db.execute(select(Product).order_by(Product.name)).scalars().all()
    product_data = [
        {
            "id": p.id,
            "name": p.name,
            "sku": p.sku,
            "price": float(p.selling_price),
            "quantity": int(p.quantity),
            "gst_rate": float(p.gst_rate),
        }
        for p in products
    ]

if not product_data:
    st.warning("No products found. Add products from the Inventory page first.")
    st.stop()

products_by_id = {p["id"]: p for p in product_data}
st.session_state.stockflow_cart = {
    int(pid): int(qty)
    for pid, qty in st.session_state.stockflow_cart.items()
    if int(pid) in products_by_id
}
for product in product_data:
    st.session_state.stockflow_gst_rates.setdefault(product["id"], product["gst_rate"])


# Add products
st.subheader("1. Add Products")
available_products = [p for p in product_data if p["quantity"] > 0]

if available_products:
    labels = {
        p["id"]: f'{p["name"]} | SKU: {p["sku"]} | Rs. {p["price"]:.2f} | Stock: {p["quantity"]}'
        for p in available_products
    }
    selected_id = st.selectbox(
        "Select product",
        options=list(labels.keys()),
        format_func=lambda pid: labels[pid],
        key="billing_selected_product",
    )
    selected_product = products_by_id[selected_id]
    quantity_to_add = st.number_input(
        "Quantity to add",
        min_value=1,
        max_value=selected_product["quantity"],
        value=1,
        step=1,
        key=f"billing_quantity_{selected_id}",
    )

    if st.button("➕ Add to Invoice", type="primary"):
        existing_quantity = st.session_state.stockflow_cart.get(selected_id, 0)
        new_quantity = existing_quantity + int(quantity_to_add)
        if new_quantity > selected_product["quantity"]:
            st.error("Requested quantity exceeds available stock.")
        else:
            st.session_state.stockflow_cart[selected_id] = new_quantity
            st.rerun()
else:
    st.info("All products are currently out of stock.")


# Billing settings
st.divider()
st.subheader("2. GST and Discount Settings")
col1, col2, col3 = st.columns(3)

with col1:
    pricing_mode = st.selectbox(
        "Pricing mode",
        options=["exclusive", "inclusive"],
        format_func=lambda value: (
            "GST exclusive (added to price)"
            if value == "exclusive"
            else "GST inclusive (included in price)"
        ),
    )
with col2:
    discount_type = st.selectbox(
        "Discount type",
        options=["none", "percentage", "fixed"],
        format_func=lambda value: {
            "none": "No discount",
            "percentage": "Percentage (%)",
            "fixed": "Fixed amount (Rs.)",
        }[value],
    )
with col3:
    discount_value = st.number_input(
        "Discount value",
        min_value=0.0,
        value=0.0,
        step=1.0,
    )

if discount_type == "percentage" and discount_value > 100:
    st.error("Percentage discount cannot exceed 100%.")


# Invoice cart
st.divider()
st.subheader("3. Current Invoice")
cart = st.session_state.stockflow_cart

if not cart:
    st.info("Your invoice is empty. Add products above.")
else:
    for product_id in list(cart):
        product = products_by_id[product_id]
        left, middle, right = st.columns([3, 2, 1])

        with left:
            st.write(f'**{product["name"]}**')
            st.caption(f'SKU: {product["sku"]}')
        with middle:
            st.write(f'Quantity: {cart[product_id]}')
            st.write(f'Unit price: Rs. {product["price"]:.2f}')
        with right:
            if st.button("Remove", key=f"remove_{product_id}"):
                del st.session_state.stockflow_cart[product_id]
                st.rerun()

        st.session_state.stockflow_gst_rates[product_id] = st.number_input(
            f'GST rate for {product["name"]} (%)',
            min_value=0.0,
            max_value=100.0,
            value=float(st.session_state.stockflow_gst_rates[product_id]),
            step=0.5,
            key=f"gst_rate_{product_id}",
        )

    try:
        calculation_items = [
            {
                "product_id": product_id,
                "name": products_by_id[product_id]["name"],
                "quantity": quantity,
                "unit_price": products_by_id[product_id]["price"],
                "gst_rate": float(st.session_state.stockflow_gst_rates[product_id]),
            }
            for product_id, quantity in cart.items()
        ]
        preview = calculate_invoice(
            items=calculation_items,
            pricing_mode=pricing_mode,
            discount_type=discount_type,
            discount_value=float(discount_value),
        )
    except (ValueError, TypeError, KeyError) as exc:
        st.error(f"Unable to calculate invoice: {exc}")
        st.stop()

    metric1, metric2, metric3, metric4 = st.columns(4)
    metric1.metric("Subtotal", f'Rs. {preview["subtotal"]:.2f}')
    metric2.metric("Discount", f'Rs. {preview["discount_amount"]:.2f}')
    metric3.metric("GST", f'Rs. {preview["gst_amount"]:.2f}')
    metric4.metric("Invoice total", f'Rs. {preview["total_amount"]:.2f}')

    with st.expander("View tax breakdown"):
        st.write(f"Pricing mode: {pricing_mode.title()}")
        st.write(f'Taxable amount: Rs. {preview["taxable_amount"]:.2f}')
        st.write(f'GST amount: Rs. {preview["gst_amount"]:.2f}')

    action1, action2 = st.columns(2)
    with action1:
        if st.button("🗑️ Clear Invoice"):
            st.session_state.stockflow_cart = {}
            st.session_state.stockflow_last_sale_id = None
            st.rerun()
    with action2:
        complete_sale = st.button(
            "✅ Complete Sale",
            type="primary",
            use_container_width=True,
        )

    if complete_sale:
        success, message, sale_id = save_sale(
            cart=cart.copy(),
            pricing_mode=pricing_mode,
            discount_type=discount_type,
            discount_value=discount_value,
            gst_rates=st.session_state.stockflow_gst_rates.copy(),
        )
        if success:
            st.session_state.stockflow_last_sale_id = sale_id
            st.session_state.stockflow_cart = {}
            st.success(f"Invoice {message} created successfully.")
            st.rerun()
        else:
            st.error(message)


# PDF download
last_sale_id = st.session_state.stockflow_last_sale_id
if last_sale_id is not None:
    st.divider()
    st.subheader("4. Download Invoice PDF")
    try:
        pdf_data = create_invoice_pdf(last_sale_id)
        st.download_button(
            "📄 Download Invoice PDF",
            data=pdf_data,
            file_name=f"StockFlow_Invoice_{last_sale_id}.pdf",
            mime="application/pdf",
        )
    except (ValueError, SQLAlchemyError) as exc:
        st.error(f"Unable to generate PDF: {exc}")


# Recent sales
st.divider()
st.subheader("5. Recent Sales History")

with SessionLocal() as db:
    recent_sales = db.execute(
        select(Sale).order_by(Sale.created_at.desc()).limit(50)
    ).scalars().all()

sales_rows = [
    {
        "Invoice": sale.invoice_number,
        "Date": sale.created_at,
        "Pricing Mode": getattr(sale, "pricing_mode", "legacy"),
        "Subtotal (Rs.)": sale.subtotal,
        "Discount (Rs.)": sale.discount_amount,
        "GST (Rs.)": sale.gst_amount,
        "Total (Rs.)": sale.total_amount,
    }
    for sale in recent_sales
]

if sales_rows:
    st.dataframe(pd.DataFrame(sales_rows), use_container_width=True, hide_index=True)
else:
    st.info("No sales have been recorded yet.")
