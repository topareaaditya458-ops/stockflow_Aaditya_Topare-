import pandas as pd
import plotly.express as px
import streamlit as st

from database.connection import SessionLocal
from database.models import Product
from ml.forecasting import forecast_product_demand, get_restock_recommendations


st.set_page_config(
    page_title="StockFlow | AI Forecasting",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 StockFlow AI Demand Forecasting")
st.caption(
    "Forecast product demand, evaluate model performance, and plan replenishment "
    "using your recorded sales history."
)
st.divider()


# Load product list without keeping a database session open during UI rendering.
with SessionLocal() as session:
    products = session.query(Product).order_by(Product.name).all()
    product_options = {
        f"{product.sku} — {product.name}": product.id
        for product in products
    }

if not product_options:
    st.warning("No products found. Add products from the Inventory page first.")
    st.stop()


st.subheader("📈 Product Demand Forecast")
top1, top2 = st.columns([3, 1])

with top1:
    selected_label = st.selectbox("Choose a product", list(product_options.keys()))

with top2:
    forecast_days = st.selectbox("Forecast horizon", [7, 14, 30], index=0)

if st.button("Generate Forecast", type="primary"):
    with st.spinner("Analysing sales history and evaluating the model..."):
        try:
            result = forecast_product_demand(
                product_options[selected_label],
                int(forecast_days),
            )
            st.session_state["stockflow_forecast_result"] = result
            st.session_state["stockflow_forecast_product"] = selected_label
            st.session_state["stockflow_forecast_days"] = int(forecast_days)
        except (ValueError, KeyError) as exc:
            st.error(f"Could not generate the forecast: {exc}")
        except Exception as exc:
            st.error(
                "Forecasting encountered an unexpected error. "
                f"Details: {type(exc).__name__}: {exc}"
            )

if "stockflow_forecast_result" in st.session_state:
    result = st.session_state["stockflow_forecast_result"]
    history = result["history"]

    st.caption(f"Product: {st.session_state.get('stockflow_forecast_product', selected_label)}")

    if not history.empty:
        historical_chart = history.copy()
        historical_chart["date"] = pd.to_datetime(historical_chart["date"])
        fig_history = px.bar(
            historical_chart,
            x="date",
            y="quantity_sold",
            title="Recorded Daily Sales",
            labels={"date": "Date", "quantity_sold": "Units sold"},
            template="plotly_dark",
        )
        st.plotly_chart(fig_history, use_container_width=True)

    if result["status"] != "success":
        st.warning(result["message"])
        st.info(
            "The system does not produce a demand forecast when history is too limited. "
            "Zero-sale days are included between recorded sale dates, but the database "
            "cannot prove that an out-of-stock day had zero customer demand."
        )
    else:
        forecast = result["forecast"].copy()
        forecast["date"] = pd.to_datetime(forecast["date"])
        history_for_chart = history[["date", "quantity_sold"]].copy()
        history_for_chart["date"] = pd.to_datetime(history_for_chart["date"])
        history_for_chart = history_for_chart.rename(
            columns={"date": "Date", "quantity_sold": "Units"}
        )
        history_for_chart["Type"] = "Historical"

        forecast_for_chart = forecast.rename(
            columns={"date": "Date", "predicted_demand": "Units"}
        )
        forecast_for_chart["Type"] = "Forecast"

        combined = pd.concat(
            [history_for_chart, forecast_for_chart],
            ignore_index=True,
        )

        predicted_total = float(forecast["predicted_demand"].sum())
        current_product_id = product_options[
            st.session_state.get("stockflow_forecast_product", selected_label)
        ]
        current_product = next(
            (p for p in products if p.id == current_product_id), None
        )
        current_stock = int(current_product.quantity) if current_product else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Forecast horizon", f"{len(forecast)} days")
        m2.metric("Predicted demand", f"{predicted_total:.1f} units")
        m3.metric("Model MAE", f"{result['mae']:.2f} units/day")
        m4.metric("Current stock", f"{current_stock} units")

        st.caption(result["message"])
        st.caption(
            f"Validation baseline MAE: {result['baseline_mae']:.2f} units/day. "
            "Lower MAE is better. Validation uses later dates than the training data."
        )

        trend = result["trend"].title()
        st.write(
            f"**Demand trend:** {trend} · "
            f"**Historical daily average:** {result['average_daily_demand']:.2f} units · "
            f"**Recent daily average:** {result['recent_average_daily_demand']:.2f} units"
        )

        fig = px.line(
            combined,
            x="Date",
            y="Units",
            color="Type",
            markers=True,
            template="plotly_dark",
            title="Historical Sales vs Future Demand Forecast",
        )
        fig.update_layout(legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Forecast Details")
        display_forecast = forecast.copy()
        display_forecast["date"] = display_forecast["date"].dt.strftime("%d %b %Y")
        display_forecast["predicted_demand"] = display_forecast[
            "predicted_demand"
        ].round(2)
        st.dataframe(
            display_forecast.rename(
                columns={
                    "date": "Date",
                    "predicted_demand": "Predicted Units",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "⬇️ Download Product Forecast (CSV)",
            data=display_forecast.to_csv(index=False).encode("utf-8"),
            file_name="stockflow_product_forecast.csv",
            mime="text/csv",
        )


st.divider()
st.subheader("📦 Restocking Recommendations")
st.caption(
    "Suggested restock = forecast demand over the selected horizon + minimum-stock "
    "buffer − current stock, floored at zero. These are planning estimates, not "
    "purchase orders; supplier lead time, pending orders, and stockouts are not modeled."
)

restock_horizon = st.selectbox(
    "Restocking forecast horizon",
    [7, 14, 30],
    index=0,
    key="stockflow_restock_horizon",
)

if st.button("Analyse All Products"):
    with st.spinner("Forecasting demand for available products..."):
        try:
            st.session_state["stockflow_recommendations"] = (
                get_restock_recommendations(int(restock_horizon))
            )
            st.session_state["stockflow_recommendations_horizon"] = int(restock_horizon)
        except (ValueError, KeyError) as exc:
            st.error(f"Could not create recommendations: {exc}")
        except Exception as exc:
            st.error(
                "Restocking analysis encountered an unexpected error. "
                f"Details: {type(exc).__name__}: {exc}"
            )

if "stockflow_recommendations" in st.session_state:
    recommendations = st.session_state["stockflow_recommendations"]

    if recommendations.empty:
        st.info("No products are available for analysis.")
    else:
        st.dataframe(
            recommendations,
            use_container_width=True,
            hide_index=True,
        )

        valid = recommendations[
            recommendations["Suggested Restock"].notna()
        ].copy()

        c1, c2, c3 = st.columns(3)
        c1.metric("Products analysed", len(recommendations))
        c2.metric("Products with forecast", len(valid))
        c3.metric(
            "Units suggested to restock",
            int(valid["Suggested Restock"].sum()) if not valid.empty else 0,
        )

        st.download_button(
            "⬇️ Download Restocking Recommendations",
            data=recommendations.to_csv(index=False).encode("utf-8"),
            file_name="stockflow_restock_recommendations.csv",
            mime="text/csv",
        )
