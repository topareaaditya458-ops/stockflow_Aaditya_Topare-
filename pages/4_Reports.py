from datetime import date, datetime, time, timedelta

import plotly.express as px
import streamlit as st

from services.reports import (
    get_sales_report,
    get_product_sales_report,
    get_inventory_report,
    get_sales_summary
)


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title='StockFlow | Reports',
    page_icon='📊',
    layout='wide'
)


# --------------------------------------------------
# HEADER
# --------------------------------------------------

st.title('📊 Reports & Business Analytics')

st.caption(
    'Analyse sales performance, product demand, '
    'profitability, and current inventory.'
)

st.divider()


# --------------------------------------------------
# REPORTING PERIOD
# --------------------------------------------------

st.subheader('🗓️ Select Reporting Period')

today = date.today()

period = st.selectbox(
    'Reporting period',
    [
        'Today',
        'Last 7 Days',
        'Last 30 Days',
        'Custom Range'
    ]
)

if period == 'Today':
    start_date = today
    end_date = today

elif period == 'Last 7 Days':
    start_date = today - timedelta(days=6)
    end_date = today

elif period == 'Last 30 Days':
    start_date = today - timedelta(days=29)
    end_date = today

else:
    col1, col2 = st.columns(2)

    with col1:
        start_date = st.date_input(
            'Start date',
            value=today - timedelta(days=6)
        )

    with col2:
        end_date = st.date_input(
            'End date',
            value=today
        )


if start_date > end_date:
    st.error('Start date cannot be after end date.')
    st.stop()


# Include the entire selected end date.
start_datetime = datetime.combine(
    start_date,
    time.min
)

end_datetime = datetime.combine(
    end_date + timedelta(days=1),
    time.min
)


# --------------------------------------------------
# LOAD REPORT DATA
# --------------------------------------------------

try:
    sales_df = get_sales_report(
        start_datetime,
        end_datetime
    )

    product_sales_df = get_product_sales_report(
        start_datetime,
        end_datetime
    )

    inventory_df = get_inventory_report()

    summary = get_sales_summary(
        sales_df,
        product_sales_df
    )

    # Defensive check: the summary must be a dictionary.
    if not isinstance(summary, dict):
        raise TypeError(
            'get_sales_summary() must return a dictionary.'
        )

except Exception as error:
    st.error('Unable to generate reports.')
    st.exception(error)
    st.stop()


# --------------------------------------------------
# SALES PERFORMANCE
# --------------------------------------------------

st.divider()

st.subheader('💰 Sales Performance')

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        'Total Revenue',
        f"₹{summary['total_revenue']:,.2f}"
    )

with col2:
    st.metric(
        'Total Invoices',
        f"{summary['invoice_count']:,}"
    )

with col3:
    st.metric(
        'Units Sold',
        f"{summary['total_units_sold']:,}"
    )


col4, col5, col6 = st.columns(3)

with col4:
    st.metric(
        'Average Invoice Value',
        f"₹{summary['average_invoice_value']:,.2f}"
    )

with col5:
    st.metric(
        'Estimated Gross Profit',
        f"₹{summary['estimated_gross_profit']:,.2f}"
    )

with col6:
    st.metric(
        'Estimated Profit Margin',
        f"{summary['profit_margin']:.2f}%"
    )

st.caption(
    'Profit is estimated using the purchase prices currently '
    'stored for products. If purchase prices change over time, '
    'historical profit may not be exact. Operating expenses '
    'and taxes are excluded.'
)


# --------------------------------------------------
# DAILY REVENUE CHART
# --------------------------------------------------

st.divider()

st.subheader('📈 Daily Revenue')

if sales_df.empty:
    st.info(
        'No sales were found in the selected reporting period.'
    )

else:
    chart_df = sales_df.copy()

    chart_df['created_at'] = (
        chart_df['created_at'].pipe(
            lambda values: __import__('pandas').to_datetime(values)
        )
    )

    chart_df['Date'] = chart_df['created_at'].dt.date

    daily_sales = (
        chart_df.groupby('Date', as_index=False)['total_amount']
        .sum()
        .sort_values('Date')
    )

    fig = px.line(
        daily_sales,
        x='Date',
        y='total_amount',
        markers=True,
        title='Revenue by Day',
        labels={
            'total_amount': 'Revenue (₹)',
            'Date': 'Date'
        },
        template='plotly_dark'
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )


# --------------------------------------------------
# PRODUCT SALES REPORT
# --------------------------------------------------

st.divider()

st.subheader('🏆 Product Sales Report')

if product_sales_df.empty:
    st.info(
        'No product sales were found in the selected period.'
    )

else:
    st.dataframe(
        product_sales_df,
        hide_index=True,
        use_container_width=True
    )


# --------------------------------------------------
# CURRENT INVENTORY
# --------------------------------------------------

st.divider()

st.subheader('📦 Current Inventory')

if inventory_df.empty:
    st.info('Your inventory is currently empty.')

else:
    st.dataframe(
        inventory_df,
        hide_index=True,
        use_container_width=True
    )


# --------------------------------------------------
# CSV EXPORTS
# --------------------------------------------------

st.divider()

st.subheader('📥 Download Reports')

col1, col2, col3 = st.columns(3)


with col1:
    st.download_button(
        label='⬇️ Sales Report',
        data=sales_df.to_csv(index=False).encode('utf-8-sig'),
        file_name='stockflow_sales_report.csv',
        mime='text/csv',
        use_container_width=True
    )


with col2:
    st.download_button(
        label='⬇️ Product Sales Report',
        data=product_sales_df.to_csv(
            index=False
        ).encode('utf-8-sig'),
        file_name='stockflow_product_sales.csv',
        mime='text/csv',
        use_container_width=True
    )


with col3:
    st.download_button(
        label='⬇️ Inventory Report',
        data=inventory_df.to_csv(
            index=False
        ).encode('utf-8-sig'),
        file_name='stockflow_inventory_report.csv',
        mime='text/csv',
        use_container_width=True
    )


st.success('Reports generated successfully.')

st.caption(
    'StockFlow | Inventory, Sales & Business Intelligence'
)