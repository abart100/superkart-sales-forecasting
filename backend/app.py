"""SuperKart sales forecasting API.

Serves the tuned XGBoost pipeline (preprocessing + model) trained in the project notebook.

Endpoints:
    GET  /                 health check: service status and the input schema
    POST /v1/predict       one product-store record as a JSON object -> forecast revenue
    POST /v1/predictbatch  CSV file upload (form field "file"), one record per row -> forecast revenue per row
"""
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

# --- Load the serialized pipeline once, when the server starts (not on every request) ---
MODEL_PATH = Path(__file__).resolve().parent / "superkart_model.joblib"
model = joblib.load(MODEL_PATH)

# --- Input schema, read from the fitted pipeline itself, so it can never drift from the deployed model ---
FEATURES = list(model.feature_names_in_)                                # the 10 features, in training order
encoder = model[0].named_transformers_["onehotencoder"]                 # the fitted one-hot encoder
KNOWN_CATEGORIES = {col: [str(c) for c in cats] for col, cats in zip(encoder.feature_names_in_, encoder.categories_)}
CATEGORICAL_FEATURES = list(KNOWN_CATEGORIES)
NUMERIC_FEATURES = [col for col in FEATURES if col not in KNOWN_CATEGORIES]

# --- Business rules for the numeric features: physically valid values (not the training range) ---
# Each rule works on a single value and on a whole column alike, so one validation serves both endpoints
NUMERIC_RULES = {
    "Product_Weight":         (lambda v: v > 0,                "must be greater than 0"),
    "Product_Allocated_Area": (lambda v: (v >= 0) & (v <= 1),  "must be a share of the display area between 0 and 1"),
    "Product_MRP":            (lambda v: v > 0,                "must be greater than 0"),
    "Store_Age_Years":        (lambda v: v >= 0,               "must be 0 or greater"),
}
assert set(NUMERIC_RULES) == set(NUMERIC_FEATURES), "every numeric model feature needs a validation rule"

LABEL_FIXES = {"Product_Sugar_Content": {"reg": "Regular"}}   # the same label cleaning as in training
MAX_ROWS_LISTED = 10                                          # row numbers listed per problem in batch errors

superkart_api = Flask("SuperKart")
superkart_api.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # uploads above 5 MB are rejected (HTTP 413)
superkart_api.json.sort_keys = False                          # keep response keys in the order they are written


# ----------------------------------------------------------------------------------------------------------
# Validation and prediction
# ----------------------------------------------------------------------------------------------------------
def where(mask, single):
    """Row numbers of a problem, for batch error messages (empty for a single record)."""
    if single:
        return ""
    rows = [str(row) for row in mask[mask].index]
    listed = ", ".join(rows[:MAX_ROWS_LISTED]) + (", ..." if len(rows) > MAX_ROWS_LISTED else "")
    return f" (row{'s' if len(rows) > 1 else ''} {listed})"


def prepare_features(frame):
    """Validate and clean raw input rows.

    Returns (features, errors, warnings): `features` holds the 10 model features in training order with numbers
    converted to numbers; `errors` lists every problem that prevents a forecast; `warnings` lists inputs the model
    can score but has not seen in training.
    """
    single = len(frame) == 1
    missing = [col for col in FEATURES if col not in frame.columns]
    if missing:
        return None, [f"missing required feature(s): {', '.join(missing)}"], []

    features = frame[FEATURES].copy()            # extra columns are ignored; columns put in the model's order
    errors, warnings = [], []

    for col in NUMERIC_FEATURES:
        raw = features[col]
        # Numbers, or text that reads as a number ("117.08"); booleans, lists, and empty values are rejected
        usable = raw.map(lambda v: isinstance(v, (int, float, str, np.number)) and not isinstance(v, (bool, np.bool_)))
        values = pd.to_numeric(raw.where(usable), errors="coerce").astype(float)
        not_number = values.isna() | ~np.isfinite(values)
        if not_number.any():
            errors.append(f"{col}{where(not_number, single)}: must be a number")
        rule, message = NUMERIC_RULES[col]
        out_of_range = ~not_number & ~rule(values)
        if out_of_range.any():
            errors.append(f"{col}{where(out_of_range, single)}: {message}")
        features[col] = values

    for col in CATEGORICAL_FEATURES:
        cleaned = features[col].map(lambda v: v.strip() if isinstance(v, str) else v).replace(LABEL_FIXES.get(col, {}))
        is_text = cleaned.map(lambda v: isinstance(v, str) and v != "")
        if not is_text.all():
            errors.append(f"{col}{where(~is_text, single)}: must be a non-empty text value")
        unseen = is_text & ~cleaned.isin(KNOWN_CATEGORIES[col])
        if unseen.any():
            values = ", ".join(sorted(set(cleaned[unseen])))
            warnings.append(
                f"{col}{where(unseen, single)}: '{values}' not seen in training - the forecast is an extrapolation "
                f"(known values: {', '.join(KNOWN_CATEGORIES[col])})"
            )
        features[col] = cleaned

    return features, errors, warnings


def forecast(features):
    """Revenue forecasts in currency units: rounded to 2 decimals, never negative."""
    return np.clip(model.predict(features), 0, None).astype(float).round(2)


def error_response(status, message, details=None):
    """A JSON error body with a short message and, if available, the list of individual problems."""
    body = {"error": message}
    if details:
        body["details"] = details
    return jsonify(body), status


# ----------------------------------------------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------------------------------------------
@superkart_api.get("/")
def health():
    """Health check, also used by Docker's HEALTHCHECK: confirms the model is loaded and shows the input schema."""
    return jsonify({
        "service": "SuperKart Sales Forecasting API",
        "status": "ok",
        "model": type(model[-1]).__name__,
        "endpoints": {
            "POST /v1/predict": "JSON object with the features below -> {'Sales': forecast}",
            "POST /v1/predictbatch": "CSV file in form field 'file' -> {'predictions': {row: forecast}}",
        },
        "features": {"numeric": NUMERIC_FEATURES, "categorical": KNOWN_CATEGORIES},
    })


@superkart_api.post("/v1/predict")
def predict_sales():
    """Forecast the revenue of one product in one store."""
    payload = request.get_json(silent=True)      # None if the body is missing or not valid JSON
    if not isinstance(payload, dict):
        return error_response(400, "the request body must be a JSON object with the product and store features",
                              [f"expected features: {', '.join(FEATURES)}"])

    features, errors, warnings = prepare_features(pd.DataFrame([payload]))
    if errors:
        return error_response(400, "invalid input - no forecast was made", errors)

    return jsonify({"Sales": float(forecast(features)[0]), "warnings": warnings})


@superkart_api.post("/v1/predictbatch")
def predict_sales_batch():
    """Forecast the revenue of every product (row) in an uploaded CSV file."""
    file = request.files.get("file")
    if file is None:
        return error_response(400, "no file received - upload the CSV file in the form field 'file'")

    try:
        frame = pd.read_csv(file)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError):
        return error_response(400, "the uploaded file could not be read as a CSV file")
    if frame.empty:
        return error_response(400, "the CSV file contains no data rows")

    features, errors, warnings = prepare_features(frame)
    if errors:
        return error_response(400, "invalid input - no forecasts were made", errors)

    predictions = forecast(features)
    return jsonify({
        "predictions": {str(row): value for row, value in zip(frame.index, predictions.tolist())},
        "rows": len(frame),
        "warnings": warnings,
    })


# ----------------------------------------------------------------------------------------------------------
# Errors: JSON responses instead of Flask's default HTML pages
# ----------------------------------------------------------------------------------------------------------
@superkart_api.errorhandler(HTTPException)
def handle_http_error(exc):
    """Unknown URL (404), wrong method (405), upload too large (413), and other HTTP errors."""
    return error_response(exc.code, exc.description)


@superkart_api.errorhandler(Exception)
def handle_unexpected_error(exc):
    """Any other failure: logged in full on the server, reported to the caller without internal details."""
    superkart_api.logger.exception("unexpected error while handling a request")
    return error_response(500, "internal server error - the forecast could not be computed")


# Local run without Docker (python app.py); in the container, gunicorn serves the app instead
if __name__ == "__main__":
    superkart_api.run(host="0.0.0.0", port=7860)
