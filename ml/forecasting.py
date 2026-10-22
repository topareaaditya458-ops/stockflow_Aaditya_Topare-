from datetime import date, timedelta

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
from sqlalchemy import func

from database.connection import SessionLocal
from database.models import Product, Sale, SaleItem


MINIMUM_TRAINING_DAYS = 14
MINIMUM_TRAINING_RECORDS = 7
MAX_FORECAST_DAYS = 90


def get_product_sales_history(product_id, start_date=None, end_date=None):
    """
    Return daily units sold for a product, including zero-sale days.

    By default, history starts at the first recorded sale. If start_date is
    supplied, the returned calendar begins there, allowing callers to include
    known zero-demand days before the first sale. Zero sales mean no recorded
    sales, not necessarily proof that customer demand was zero.
    """
    with SessionLocal() as session:
        query = (
            session.query(
                func.date(Sale.created_at).label("sale_date"),
                func.sum(SaleItem.quantity).label("quantity_sold"),
            )
            .join(SaleItem, SaleItem.sale_id == Sale.id)
            .filter(SaleItem.product_id == product_id)
            .group_by(func.date(Sale.created_at))
            .order_by(func.date(Sale.created_at))
        )
        if start_date is not None:
            query = query.filter(func.date(Sale.created_at) >= start_date)
        if end_date is not None:
            query = query.filter(func.date(Sale.created_at) <= end_date)
        results = query.all()

    if not results:
        return pd.DataFrame(columns=["date", "quantity_sold"])

    sales_df = pd.DataFrame(results, columns=["date", "quantity_sold"])
    sales_df["date"] = pd.to_datetime(sales_df["date"])
    sales_df["quantity_sold"] = pd.to_numeric(
        sales_df["quantity_sold"], errors="coerce"
    ).fillna(0)

    first_date = (
        pd.Timestamp(start_date)
        if start_date is not None
        else sales_df["date"].min()
    )
    last_date = (
        min(pd.Timestamp(end_date), sales_df["date"].max())
        if end_date is not None
        else sales_df["date"].max()
    )

    if last_date < first_date:
        return pd.DataFrame(columns=["date", "quantity_sold"])

    daily = sales_df.set_index("date").sort_index()
    full_range = pd.date_range(first_date, last_date, freq="D")
    daily = daily.reindex(full_range, fill_value=0)
    daily.index.name = "date"
    daily = daily.reset_index()
    daily["quantity_sold"] = daily["quantity_sold"].fillna(0).clip(lower=0)
    daily["quantity_sold"] = daily["quantity_sold"].astype(float)
    return daily


def _insufficient_result(history, message):
    return {
        "status": "insufficient_data",
        "message": message,
        "history": history,
        "forecast": pd.DataFrame(columns=["date", "predicted_demand"]),
        "mae": None,
        "baseline_mae": None,
        "model_name": None,
        "baseline_name": "Moving average",
        "trend": "unknown",
        "average_daily_demand": None,
        "recent_average_daily_demand": None,
        "total_historical_units": (
            float(history["quantity_sold"].sum()) if not history.empty else 0.0
        ),
    }


def forecast_product_demand(product_id, forecast_days=7):
    """
    Forecast daily demand with a linear trend and compare it with a naive
    moving-average baseline using a chronological holdout.

    Returns the original keys (status, message, history, forecast, mae) plus
    baseline metrics and simple trend indicators for the UI.
    """
    if not isinstance(forecast_days, int) or not 1 <= forecast_days <= MAX_FORECAST_DAYS:
        raise ValueError(f"Forecast period must be between 1 and {MAX_FORECAST_DAYS} days.")

    history = get_product_sales_history(product_id)
    if history.empty:
        return _insufficient_result(
            history, "No sales history is available for this product."
        )

    history = history.copy()
    history["date"] = pd.to_datetime(history["date"])
    history["quantity_sold"] = pd.to_numeric(
        history["quantity_sold"], errors="coerce"
    ).fillna(0).clip(lower=0)
    history["day_number"] = np.arange(len(history), dtype=int)

    total_units = float(history["quantity_sold"].sum())
    if len(history) < MINIMUM_TRAINING_DAYS or total_units < MINIMUM_TRAINING_RECORDS:
        return _insufficient_result(
            history,
            "More history is needed for a useful forecast. Aim for at least "
            "14 calendar days and 7 units sold. Predictions are intentionally "
            "withheld until these minimums are met.",
        )

    # Keep the final 20% of dates as a chronological validation period.
    split_index = max(2, int(len(history) * 0.8))
    split_index = min(split_index, len(history) - 1)
    train = history.iloc[:split_index]
    validation = history.iloc[split_index:]

    if len(train) < 2 or validation.empty:
        return _insufficient_result(
            history, "There is not enough data for chronological model evaluation."
        )

    x_train = train[["day_number"]]
    y_train = train["quantity_sold"]
    x_validation = validation[["day_number"]]
    y_validation = validation["quantity_sold"]

    model = LinearRegression()
    model.fit(x_train, y_train)
    validation_predictions = np.clip(model.predict(x_validation), 0, None)
    model_mae = float(mean_absolute_error(y_validation, validation_predictions))

    # Baseline: predict each validation day using the mean of the preceding
    # seven training/observed days, never using future validation values.
    observed = list(train["quantity_sold"].astype(float))
    baseline_predictions = []
    for actual in validation["quantity_sold"].astype(float):
        baseline_predictions.append(float(np.mean(observed[-7:])))
        observed.append(float(actual))
    baseline_mae = float(
        mean_absolute_error(y_validation, np.clip(baseline_predictions, 0, None))
    )

    final_model = LinearRegression()
    final_model.fit(history[["day_number"]], history["quantity_sold"])

    future_numbers = np.arange(
        len(history), len(history) + forecast_days, dtype=int
    )
    future = pd.DataFrame({"day_number": future_numbers})
    predictions = np.clip(final_model.predict(future[["day_number"]]), 0, None)
    future_dates = pd.date_range(
        history["date"].max() + pd.Timedelta(days=1),
        periods=forecast_days,
        freq="D",
    )
    future["date"] = future_dates
    future["predicted_demand"] = np.round(predictions, 2)
    future = future[["date", "predicted_demand"]]

    recent_window = min(7, len(history))
    recent_avg = float(history["quantity_sold"].tail(recent_window).mean())
    overall_avg = float(history["quantity_sold"].mean())
    if recent_avg > overall_avg * 1.10:
        trend = "rising"
    elif recent_avg < overall_avg * 0.90:
        trend = "declining"
    else:
        trend = "stable"

    if model_mae < baseline_mae:
        message = (
            "The linear trend model performed better than the moving-average "
            "baseline on the chronological holdout."
        )
    elif model_mae > baseline_mae:
        message = (
            "The moving-average baseline performed better on the holdout. "
            "Treat the linear trend forecast cautiously."
        )
    else:
        message = "The linear trend model and moving-average baseline had equal holdout MAE."

    return {
        "status": "success",
        "message": message,
        "history": history.drop(columns=["day_number"]),
        "forecast": future,
        "mae": model_mae,
        "baseline_mae": baseline_mae,
        "model_name": "Linear Regression",
        "baseline_name": "7-day trailing moving average",
        "trend": trend,
        "average_daily_demand": overall_avg,
        "recent_average_daily_demand": recent_avg,
        "total_historical_units": total_units,
    }


def get_restock_recommendations(forecast_days=7):
    """
    Create non-binding restock estimates. Recommendations are based on forecast
    demand plus the product's configured minimum-stock buffer, less current
    stock. Supplier lead time and confirmed purchase orders are not modeled.
    """
    if not isinstance(forecast_days, int) or not 1 <= forecast_days <= MAX_FORECAST_DAYS:
        raise ValueError(f"Forecast period must be between 1 and {MAX_FORECAST_DAYS} days.")

    with SessionLocal() as session:
        products = session.query(Product).order_by(Product.name).all()
        product_data = [
            {
                "id": product.id,
                "name": product.name,
                "sku": product.sku,
                "quantity": int(product.quantity),
                "minimum_stock": int(product.minimum_stock),
            }
            for product in products
        ]

    recommendations = []
    for product in product_data:
        result = forecast_product_demand(product["id"], forecast_days)

        if result["status"] != "success":
            recommendations.append({
                "SKU": product["sku"],
                "Product": product["name"],
                "Current Stock": product["quantity"],
                "Minimum Stock": product["minimum_stock"],
                "Forecast Status": "Insufficient history",
                "Forecast Demand": None,
                "Suggested Restock": None,
                "Demand Trend": "Unknown",
                "Model MAE": None,
            })
            continue

        forecast_demand = max(
            0, int(np.ceil(result["forecast"]["predicted_demand"].sum()))
        )
        target_stock = forecast_demand + product["minimum_stock"]
        suggested_restock = max(0, target_stock - product["quantity"])

        recommendations.append({
            "SKU": product["sku"],
            "Product": product["name"],
            "Current Stock": product["quantity"],
            "Minimum Stock": product["minimum_stock"],
            "Forecast Status": "Forecast available",
            "Forecast Demand": forecast_demand,
            "Suggested Restock": suggested_restock,
            "Demand Trend": result["trend"].title(),
            "Model MAE": round(result["mae"], 2),
        })

    return pd.DataFrame(recommendations)
