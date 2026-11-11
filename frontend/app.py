"""SuperKart sales forecasting - web app for store and category managers.

A Streamlit user interface for the SuperKart forecasting API (the backend container):
    - Single product: pick a store and describe a product -> forecast revenue
    - Batch forecast: upload a CSV file with many products -> forecasts for every row, downloadable as CSV
"""
import io
import os

import pandas as pd
import requests
import streamlit as st

# --- Connection to the backend: its container name on the shared Docker network (overridable for local runs) ---
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:7860").rstrip("/")
TIMEOUT_SECONDS = 30

# --- Business knowledge the form needs (taken from the training data) ---
REFERENCE_YEAR = 2025      # Store_Age_Years = REFERENCE_YEAR - year of establishment, as in model training
KNOWN_STORES = {           # the four stores the model was trained on, with their fixed attributes
    "OUT001": {"Store_Type": "Supermarket Type1", "Store_Size": "High", "Store_Location_City_Type": "Tier 2", "Established": 1987},
    "OUT002": {"Store_Type": "Food Mart", "Store_Size": "Small", "Store_Location_City_Type": "Tier 3", "Established": 1998},
    "OUT003": {"Store_Type": "Departmental Store", "Store_Size": "Medium", "Store_Location_City_Type": "Tier 1", "Established": 1999},
    "OUT004": {"Store_Type": "Supermarket Type2", "Store_Size": "Medium", "Store_Location_City_Type": "Tier 2", "Established": 2009},
}
OTHER_STORE = "Other store - enter its attributes"
PRODUCT_GROUPS = {"FD": "Food (FD)", "DR": "Drinks (DR)", "NC": "Non-consumables (NC)"}
FEATURES = [               # the API's input contract, in the model's column order
    "Product_Weight", "Product_Sugar_Content", "Product_Allocated_Area", "Product_MRP", "Store_Size",
    "Store_Location_City_Type", "Store_Type", "Product_Id_char", "Store_Age_Years", "Product_Type_Category",
]
# Valid categories if the API's schema cannot be loaded (normally they are read from the API, i.e. from the model)
FALLBACK_CATEGORIES = {
    "Product_Sugar_Content": ["Low Sugar", "No Sugar", "Regular"],
    "Store_Size": ["High", "Medium", "Small"],
    "Store_Location_City_Type": ["Tier 1", "Tier 2", "Tier 3"],
    "Store_Type": ["Departmental Store", "Food Mart", "Supermarket Type1", "Supermarket Type2"],
    "Product_Id_char": ["DR", "FD", "NC"],
    "Product_Type_Category": ["Non Perishables", "Perishables"],
}


# ----------------------------------------------------------------------------------------------------------
# Calls to the backend API (no Streamlit code here: each function returns (result, error message))
# ----------------------------------------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def load_schema(backend_url):
    """The API's health check and input schema; cached for a minute, so the page does not call the API on every click."""
    response = requests.get(f"{backend_url}/", timeout=5)
    response.raise_for_status()
    return response.json()


def fetch_schema():
    """The schema, or None if the API is not reachable. Failures raise inside load_schema and are therefore
    not cached, so the page connects as soon as the backend is up (e.g. when the frontend container starts first)."""
    try:
        return load_schema(BACKEND_URL)
    except (requests.RequestException, ValueError):
        return None


def api_error(response):
    """A readable message from an API error response, including the individual problems the API lists."""
    try:
        body = response.json()
        details = body.get("details", [])
        return body.get("error", f"HTTP {response.status_code}") + "".join(f"\n- {detail}" for detail in details)
    except ValueError:
        return f"HTTP {response.status_code}: the API returned an unexpected response"


def request_forecast(payload):
    """POST one record to /v1/predict. Returns ({'Sales', 'warnings'}, None) or (None, error message)."""
    try:
        response = requests.post(f"{BACKEND_URL}/v1/predict", json=payload, timeout=TIMEOUT_SECONDS)
    except requests.RequestException:
        return None, f"The forecasting API is not reachable at {BACKEND_URL}."
    return (response.json(), None) if response.ok else (None, api_error(response))


def request_batch_forecast(file_name, file_bytes):
    """POST a CSV file to /v1/predictbatch. Returns ({'predictions', 'rows', 'warnings'}, None) or (None, error message)."""
    try:
        response = requests.post(f"{BACKEND_URL}/v1/predictbatch",
                                 files={"file": (file_name, file_bytes, "text/csv")}, timeout=TIMEOUT_SECONDS)
    except requests.RequestException:
        return None, f"The forecasting API is not reachable at {BACKEND_URL}."
    return (response.json(), None) if response.ok else (None, api_error(response))


# ----------------------------------------------------------------------------------------------------------
# Page layout
# ----------------------------------------------------------------------------------------------------------
st.set_page_config(page_title="SuperKart Sales Forecast", page_icon="🛒", layout="wide")
# Less empty space above and below the content (Streamlit's default top padding is about 6rem)
st.markdown("<style>[data-testid='stMainBlockContainer'] {padding-top: 2.5rem; padding-bottom: 1rem;}</style>",
            unsafe_allow_html=True)

schema = fetch_schema()
categories = schema["features"]["categorical"] if schema else FALLBACK_CATEGORIES

with st.sidebar:
    st.header("Forecasting API")
    if schema:
        st.success(f"Connected - model: {schema['model']}")
    else:
        st.error(f"Not reachable at {BACKEND_URL}. Forecasts are unavailable until the backend is running.")
    st.caption(f"Backend: {BACKEND_URL}")
    st.divider()
    st.markdown(
        "**About the forecasts**\n\n"
        "The model forecasts the total revenue of a product in a store (test-set accuracy: R-squared 0.93, "
        "typical error about 4%). It learned from four stores, so forecasts for other store profiles are "
        "extrapolations and are flagged with a warning."
    )

st.title("🛒 SuperKart Sales Forecast")
st.caption("Forecast the total revenue of a product in a store - for a single product, or for a whole file of products.")

tab_single, tab_batch = st.tabs(["Single product", "Batch forecast (CSV)"])

# --- Single product: store, product, and price details side by side -> one forecast ---
with tab_single:
    col_store, col_product, col_numbers = st.columns(3, gap="medium")

    with col_store:
        st.subheader("Store")
        store_choice = st.selectbox("Store", list(KNOWN_STORES) + [OTHER_STORE],
                                    help="The four stores the model knows fill in their attributes automatically.")
        if store_choice in KNOWN_STORES:
            store = KNOWN_STORES[store_choice]
            st.info(f"{store['Store_Type']} | size {store['Store_Size']} | {store['Store_Location_City_Type']} city "
                    f"| established {store['Established']}")
        else:
            store = {
                "Store_Type": st.selectbox("Store type", categories["Store_Type"]),
                "Store_Size": st.selectbox("Store size", categories["Store_Size"]),
                "Store_Location_City_Type": st.selectbox("City tier", categories["Store_Location_City_Type"],
                                                         help="Tier 1 = largest cities, Tier 3 = smallest"),
                "Established": st.number_input("Year of establishment", min_value=1900, max_value=REFERENCE_YEAR,
                                               value=2000, step=1),
            }
            st.warning("The model was trained on four stores only - a forecast for a different store profile "
                       "is an extrapolation.")

    with col_product:
        st.subheader("Product")
        product_group = st.selectbox("Product group", list(PRODUCT_GROUPS), format_func=PRODUCT_GROUPS.get)
        # Drinks and non-consumables are never perishable (training data), so only food offers both options
        category_options = categories["Product_Type_Category"] if product_group == "FD" else ["Non Perishables"]
        product_category = st.selectbox("Product category", category_options,
                                        help="Perishables: dairy, meat, seafood, fruits and vegetables, breads, breakfast")
        sugar_content = st.selectbox("Sugar content", categories["Product_Sugar_Content"])

    with col_numbers:
        st.subheader("Price and size")
        product_mrp = st.number_input("Maximum retail price (MRP)", min_value=1.0, max_value=1000.0, value=146.74, step=1.0)
        product_weight = st.number_input("Weight", min_value=0.1, max_value=100.0, value=12.66, step=0.1)
        allocated_area = st.number_input("Share of the store's display area", min_value=0.001, max_value=1.0,
                                         value=0.056, step=0.001, format="%.3f",
                                         help="Display area of this product / total display area of the store")

    payload = {
        "Product_Weight": product_weight,
        "Product_Sugar_Content": sugar_content,
        "Product_Allocated_Area": allocated_area,
        "Product_MRP": product_mrp,
        "Store_Size": store["Store_Size"],
        "Store_Location_City_Type": store["Store_Location_City_Type"],
        "Store_Type": store["Store_Type"],
        "Product_Id_char": product_group,
        "Store_Age_Years": REFERENCE_YEAR - int(store["Established"]),
        "Product_Type_Category": product_category,
    }

    # Button and result on one row: the forecast appears next to the button, not below the form
    col_button, col_result, col_details = st.columns([1, 1, 2], vertical_alignment="center")
    if col_button.button("Forecast revenue", type="primary", key="predict_single"):
        with st.spinner("Requesting the forecast..."):
            result, error = request_forecast(payload)
        if error:
            st.error(error)
        else:
            col_result.metric("Forecast revenue", f"{result['Sales']:,.2f}")
            with col_details.expander("Request sent to the API"):
                st.json(payload)
            for warning in result["warnings"]:
                st.warning(warning)

# --- Batch forecast: CSV upload -> forecasts for every row ---
with tab_batch:
    col_intro, col_template = st.columns([3, 1], vertical_alignment="bottom")
    col_intro.write("Upload a CSV file with one product per row and these 10 columns (extra columns are ignored):")
    col_intro.code(", ".join(FEATURES), language=None)
    template = pd.DataFrame([dict(zip(FEATURES, [12.66, "Low Sugar", 0.056, 146.74, "Medium", "Tier 2",
                                                 "Supermarket Type2", "FD", 16, "Non Perishables"]))])
    col_template.download_button("Download a CSV template", template.to_csv(index=False), "superkart_template.csv",
                                 "text/csv")

    uploaded = st.file_uploader("CSV file", type=["csv"])
    if uploaded is not None:
        file_bytes = uploaded.getvalue()
        try:
            batch = pd.read_csv(io.BytesIO(file_bytes))
        except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError):
            st.error("The file could not be read as a CSV file.")
            st.stop()
        with st.expander(f"Preview: {uploaded.name} - {len(batch):,} rows x {batch.shape[1]} columns"):
            st.dataframe(batch.head(), hide_index=True)

        if st.button("Forecast all rows", type="primary", key="predict_batch"):
            with st.spinner(f"Requesting forecasts for {len(batch):,} rows..."):
                result, error = request_batch_forecast(uploaded.name, file_bytes)
            if error:
                st.error(error)
            else:
                forecasts = pd.Series(result["predictions"], dtype=float)
                forecasts.index = forecasts.index.astype(int)      # keys are row numbers sent as text
                results = batch.assign(Forecast_Sales=forecasts)

                col_rows, col_total, col_mean, col_download = st.columns(4, vertical_alignment="center")
                col_rows.metric("Products forecast", f"{result['rows']:,}")
                col_total.metric("Total forecast revenue", f"{forecasts.sum():,.2f}")
                col_mean.metric("Average per product", f"{forecasts.mean():,.2f}")
                col_download.download_button("Download the forecasts (CSV)", results.to_csv(index=False),
                                             f"forecast_{uploaded.name}", "text/csv", type="primary")
                for warning in result["warnings"]:
                    st.warning(warning)
                st.dataframe(results, hide_index=True)
