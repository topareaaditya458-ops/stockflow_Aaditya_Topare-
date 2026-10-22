import streamlit as st
import plotly.express as px

from services.analytics import (
    get_dashboard_metrics,
    get_sales_chart_data,
    get_low_stock_products,
    get_recent_sales,
    get_best_selling_products
)


st.set_page_config(
    page_title='StockFlow | Dashboard',
    page_icon='📦',
    layout='wide'
)


# --------------------------------------------------
# DASHBOARD STYLING
# --------------------------------------------------

st.markdown("""
<style>
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
    }

    [data-testid="stSidebar"] {
        background-color: #151922;
    }

    [data-testid="stMetric"] {
        background-color: #1B2230;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #30394A;
    }

    div[data-testid="stMetricValue"] {
        color: #55D6BE;
    }
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------
# SIDEBAR BRANDING
# --------------------------------------------------

st.sidebar.title('📦 StockFlow')
st.sidebar.caption('Inventory & Sales Intelligence')
st.sidebar.divider()


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

st.title('📊 Dashboard')
st.caption('Your business at a glance')

st.divider()


try:
    metrics = get_dashboard_metrics()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            'Total Revenue',
            f"₹{metrics['total_revenue']:,.2f}"
        )

    with col2:
        st.metric(
            'Total Products',
            f"{metrics['total_products']:,}"
        )

    with col3:
        st.metric(
            'Inventory Value',
            f"₹{metrics['inventory_value']:,.2f}"
        )

    with col4:
        st.metric(
            'Low-Stock Items',
            f"{metrics['low_stock_count']:,}"
        )

    st.divider()

    # Sales chart and low-stock alerts
    left, right = st.columns([2, 1])

    with left:
        st.subheader('📈 Sales Overview')

        sales_data = get_sales_chart_data()

        if not sales_data.empty:
            fig = px.line(
                sales_data,
                x='Date',
                y='Revenue',
                markers=True,
                template='plotly_dark',
                title='Daily Revenue'
            )

            fig.update_layout(
                paper_bgcolor='#0E1117',
                plot_bgcolor='#151922',
                margin=dict(
                    l=20,
                    r=20,
                    t=50,
                    b=20
                )
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

        else:
            st.info(
                'No sales yet. Your sales chart will appear here.'
            )

    with right:
        st.subheader('⚠️ Low-Stock Alerts')

        low_stock = get_low_stock_products()

        if low_stock:
            st.dataframe(
                low_stock,
                hide_index=True,
                use_container_width=True
            )
        else:
            st.success('No low-stock items!')

    st.divider()

    # Best-selling products and recent transactions
    left, right = st.columns(2)

    with left:
        st.subheader('🏆 Best-Selling Products')

        best_sellers = get_best_selling_products()

        if not best_sellers.empty:
            fig = px.bar(
                best_sellers,
                x='Units Sold',
                y='Product',
                orientation='h',
                template='plotly_dark',
                color='Units Sold'
            )

            fig.update_layout(
                paper_bgcolor='#0E1117',
                plot_bgcolor='#151922',
                showlegend=False,
                margin=dict(
                    l=20,
                    r=20,
                    t=20,
                    b=20
                )
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

        else:
            st.info(
                'Best-selling products will appear after your first sale.'
            )

    with right:
        st.subheader('🧾 Recent Transactions')

        recent_sales = get_recent_sales()

        if recent_sales:
            st.dataframe(
                recent_sales,
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info('No transactions recorded yet.')

    st.divider()

    st.caption(
        'StockFlow | Inventory & Sales Management'
    )

except Exception as error:
    st.error('Unable to load dashboard data.')
    st.exception(error)