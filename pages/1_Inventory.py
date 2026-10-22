import math

import pandas as pd
import streamlit as st

from services.inventory import (
    get_all_products,
    add_product,
    update_product,
    delete_product,
)

st.set_page_config(
    page_title="StockFlow | Inventory",
    page_icon="📦",
    layout="wide",
)

st.title("📦 Inventory Management")
st.caption("Manage products, monitor stock health, and plan replenishment.")
st.divider()


def safe_number(value, default=0.0):
    """Convert a database value to a number without crashing on None."""
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def get_stock_status(quantity, minimum_stock):
    quantity = safe_number(quantity)
    minimum_stock = safe_number(minimum_stock)
    if quantity <= 0:
        return "🔴 Out of Stock"
    if quantity <= minimum_stock:
        return "🟠 Low Stock"
    return "🟢 Healthy"


# Load all products once for summary, alerts, editing, and restocking.
try:
    products = get_all_products() or []
except Exception as exc:
    st.error("Could not load inventory from the database.")
    st.exception(exc)
    st.stop()

total_products = len(products)
total_units = sum(safe_number(p.get("quantity")) for p in products)
inventory_value = sum(
    safe_number(p.get("purchase_price")) * safe_number(p.get("quantity"))
    for p in products
)
out_of_stock = sum(safe_number(p.get("quantity")) <= 0 for p in products)
low_stock = sum(
    safe_number(p.get("quantity")) > 0
    and safe_number(p.get("quantity")) <= safe_number(p.get("minimum_stock", 5))
    for p in products
)
healthy_stock = total_products - out_of_stock - low_stock

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Products", total_products)
col2.metric("Total Units", f"{total_units:,.0f}")
col3.metric("Inventory Value", f"₹{inventory_value:,.2f}")
col4.metric("Out of Stock", out_of_stock)
col5.metric("Low Stock", low_stock)

st.divider()

# Automated stock alerts and suggested replenishment.
st.subheader("🚦 Inventory Health & Restocking")

if not products:
    st.info("Add your first product to start monitoring inventory.")
else:
    alert_rows = []
    restock_cost = 0.0
    for product in products:
        quantity = safe_number(product.get("quantity"))
        minimum = safe_number(product.get("minimum_stock", 5))
        purchase_price = safe_number(product.get("purchase_price"))
        # Basic replenishment brings stock back to the minimum level.
        suggested_qty = max(0, math.ceil(minimum - quantity))
        estimated_cost = suggested_qty * purchase_price
        status = get_stock_status(quantity, minimum)
        restock_cost += estimated_cost
        if suggested_qty > 0:
            alert_rows.append({
                "Priority": "🔴 Urgent" if quantity <= 0 else "🟠 Reorder",
                "SKU": product.get("sku", ""),
                "Product": product.get("name", ""),
                "Category": product.get("category", ""),
                "Current Stock": int(quantity),
                "Minimum Stock": int(minimum),
                "Suggested Restock": suggested_qty,
                "Purchase Price (₹)": purchase_price,
                "Estimated Cost (₹)": estimated_cost,
                "Stock Status": status,
            })

    urgent_col, low_col, healthy_col, cost_col = st.columns(4)
    urgent_col.metric("Urgent Reorders", out_of_stock)
    low_col.metric("Low-Stock Items", low_stock)
    healthy_col.metric("Healthy Products", healthy_stock)
    cost_col.metric("Estimated Replenishment Cost", f"₹{restock_cost:,.2f}")

    if alert_rows:
        restock_df = pd.DataFrame(alert_rows)
        st.warning(
            f"{len(alert_rows)} product(s) need replenishment. "
            "Suggested quantities bring stock back to each product's minimum level."
        )
        st.dataframe(
            restock_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Purchase Price (₹)": st.column_config.NumberColumn(format="₹%.2f"),
                "Estimated Cost (₹)": st.column_config.NumberColumn(format="₹%.2f"),
            },
        )
        st.download_button(
            "⬇️ Download Restocking Report (CSV)",
            data=restock_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="stockflow_restocking_report.csv",
            mime="text/csv",
            use_container_width=False,
        )
    else:
        st.success("All products are above their minimum stock levels.")

    with st.expander("🤖 Add AI Forecast-Based Reorder Suggestions", expanded=False):
        st.caption(
            "Optional: uses the existing forecasting module. Forecast suggestions are shown "
            "only when enough sales history is available; otherwise the basic minimum-stock "
            "recommendation above remains available."
        )
        horizon = st.selectbox(
            "Forecast horizon",
            [7, 14, 30],
            format_func=lambda days: f"Next {days} days",
            key="inventory_forecast_horizon",
        )
        if st.button("Generate AI Restocking Suggestions", key="generate_inventory_ai_restock"):
            try:
                from ml.forecasting import get_restock_recommendations

                with st.spinner("Analysing sales history..."):
                    forecast_df = get_restock_recommendations(forecast_days=horizon)

                if forecast_df is None or forecast_df.empty:
                    st.info("No forecast recommendations are available yet.")
                else:
                    st.dataframe(forecast_df, use_container_width=True, hide_index=True)
                    st.download_button(
                        "⬇️ Download AI Restocking Suggestions (CSV)",
                        data=forecast_df.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"stockflow_ai_restock_{horizon}_days.csv",
                        mime="text/csv",
                        key="download_inventory_ai_restock",
                    )
            except Exception as exc:
                st.error("Could not generate AI restocking suggestions.")
                st.caption(
                    "Check that ml/forecasting.py is installed and its function "
                    "get_restock_recommendations(forecast_days=...) is available."
                )
                st.exception(exc)

st.divider()

# Add product form
with st.expander("➕ Add New Product", expanded=False):
    with st.form("add_product_form", clear_on_submit=True):
        left, right = st.columns(2)

        with left:
            sku = st.text_input("SKU / Product Code")
            name = st.text_input("Product Name")
            category = st.text_input("Category")
            purchase_price = st.number_input(
                "Purchase Price (₹)", min_value=0.0, value=0.0, step=10.0
            )

        with right:
            selling_price = st.number_input(
                "Selling Price (₹)", min_value=0.0, value=0.0, step=10.0
            )
            quantity = st.number_input(
                "Initial Stock Quantity", min_value=0, value=0, step=1
            )
            minimum_stock = st.number_input(
                "Minimum Stock Level", min_value=0, value=5, step=1
            )

        submitted = st.form_submit_button("Add Product", use_container_width=True)
        if submitted:
            if not sku.strip() or not name.strip() or not category.strip():
                st.error("Please fill in the SKU, product name, and category.")
            elif selling_price < purchase_price:
                st.warning(
                    "The selling price is below the purchase price. "
                    "Please confirm that this is intentional."
                )
                confirmed = st.checkbox(
                    "I confirm that selling below purchase price is intentional.",
                    key="confirm_below_cost",
                )
                if confirmed:
                    success, message = add_product(
                        sku.strip(), name.strip(), category.strip(),
                        purchase_price, selling_price, quantity, minimum_stock
                    )
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
            else:
                success, message = add_product(
                    sku.strip(), name.strip(), category.strip(),
                    purchase_price, selling_price, quantity, minimum_stock
                )
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

st.divider()

# Search and display products
st.subheader("🔎 Product Inventory")
search = st.text_input(
    "Search by product name, SKU, or category",
    placeholder="Enter a product name, SKU, or category...",
)
try:
    filtered_products = get_all_products(search) or []
except Exception as exc:
    st.error("Could not search inventory.")
    st.exception(exc)
    filtered_products = []

if filtered_products:
    dataframe = pd.DataFrame(filtered_products)
    rename_columns = {
        "id": "ID",
        "sku": "SKU",
        "name": "Product Name",
        "category": "Category",
        "purchase_price": "Purchase Price (₹)",
        "selling_price": "Selling Price (₹)",
        "quantity": "Stock",
        "minimum_stock": "Minimum Stock",
        "created_at": "Created At",
    }
    dataframe = dataframe.rename(columns=rename_columns)
    dataframe["Stock Status"] = dataframe.apply(
        lambda row: get_stock_status(row["Stock"], row["Minimum Stock"]), axis=1
    )
    st.dataframe(
        dataframe,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Purchase Price (₹)": st.column_config.NumberColumn(format="₹%.2f"),
            "Selling Price (₹)": st.column_config.NumberColumn(format="₹%.2f"),
        },
    )
else:
    st.info("No products found for this search. Add a product above if needed.")

st.divider()

# Edit product
st.subheader("✏️ Edit Product")
if products:
    product_options = {
        f"{p.get('sku', '')} — {p.get('name', '')} (ID: {p.get('id')})": p
        for p in products
    }
    selected_label = st.selectbox("Select a product to edit", list(product_options))
    selected_product = product_options[selected_label]

    with st.form("edit_product_form"):
        left, right = st.columns(2)
        with left:
            edit_sku = st.text_input("SKU", value=str(selected_product.get("sku") or ""))
            edit_name = st.text_input(
                "Product Name", value=str(selected_product.get("name") or "")
            )
            edit_category = st.text_input(
                "Category", value=str(selected_product.get("category") or "")
            )
            edit_purchase_price = st.number_input(
                "Purchase Price (₹)", min_value=0.0,
                value=safe_number(selected_product.get("purchase_price")),
                step=10.0, key="edit_purchase_price",
            )
        with right:
            edit_selling_price = st.number_input(
                "Selling Price (₹)", min_value=0.0,
                value=safe_number(selected_product.get("selling_price")),
                step=10.0, key="edit_selling_price",
            )
            edit_quantity = st.number_input(
                "Stock Quantity", min_value=0,
                value=max(0, int(safe_number(selected_product.get("quantity")))),
                step=1, key="edit_quantity",
            )
            edit_minimum_stock = st.number_input(
                "Minimum Stock", min_value=0,
                value=max(0, int(safe_number(selected_product.get("minimum_stock"), 5))),
                step=1, key="edit_minimum_stock",
            )

        update_submitted = st.form_submit_button("Save Changes", use_container_width=True)
        if update_submitted:
            if not edit_sku.strip() or not edit_name.strip() or not edit_category.strip():
                st.error("SKU, product name, and category are required.")
            else:
                success, message = update_product(
                    selected_product["id"],
                    edit_sku.strip(),
                    edit_name.strip(),
                    edit_category.strip(),
                    edit_purchase_price,
                    edit_selling_price,
                    edit_quantity,
                    edit_minimum_stock,
                )
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

    st.divider()
    st.subheader("🗑️ Delete Product")
    st.warning(
        "For data integrity, products with stock remaining cannot be deleted. "
        "Products referenced by sales history may also be protected by the database."
    )
    confirm_delete = st.checkbox(
        "I understand that deleting a product is permanent.",
        key="confirm_delete_product",
    )
    if st.button(
        "Delete Selected Product", type="secondary", disabled=not confirm_delete
    ):
        success, message = delete_product(selected_product["id"])
        if success:
            st.success(message)
            st.rerun()
        else:
            st.error(message)
else:
    st.info("Add a product first to enable editing and deletion.")
