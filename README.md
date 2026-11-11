# SuperKart Sales Forecasting - Deployment

Forecasts the total revenue of a product in a SuperKart store. Two Docker containers:

| Folder | Service | Port |
|:---|:---|:---|
| `backend/` | Flask REST API (gunicorn) serving the tuned XGBoost pipeline `superkart_model.joblib` | 7860 |
| `frontend/` | Streamlit web app for single-product and batch (CSV) forecasts | 8501 |

## Run in a GitHub Codespace (or any machine with Docker)

```bash
docker network create superkart-net

cd backend
docker build -t superkart-backend .
docker run -d --name backend --network superkart-net -p 7860:7860 superkart-backend

cd ../frontend
docker build -t superkart-frontend .
docker run -d --name frontend --network superkart-net -p 8501:8501 superkart-frontend

docker ps    # both containers should report "(healthy)" after about 30 seconds
```

In a Codespace, set ports 7860 and 8501 to **Public** in the PORTS tab, then open the 8501 address for the web app.
The frontend reaches the backend by its container name (`http://backend:7860`) on the shared network.

## API

| Endpoint | Request | Response |
|:---|:---|:---|
| `GET /` | - | Status and input schema |
| `POST /v1/predict` | JSON object with the 10 features | `{"Sales": ..., "warnings": [...]}` |
| `POST /v1/predictbatch` | CSV file in form field `file` | `{"predictions": {"0": ..., ...}, "rows": n, "warnings": [...]}` |

Features: `Product_Weight, Product_Sugar_Content, Product_Allocated_Area, Product_MRP, Store_Size, Store_Location_City_Type, Store_Type, Product_Id_char, Store_Age_Years, Product_Type_Category`

## Stop and clean up

```bash
docker stop frontend backend && docker rm frontend backend && docker network rm superkart-net
```
