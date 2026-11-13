# SuperKart Sales Forecasting - Deployment

Forecasts the total revenue of a product in a SuperKart store. Two Docker containers:

| Folder | Service | Port |
|:---|:---|:---|
| `backend/` | Flask REST API (gunicorn) serving the tuned XGBoost pipeline `superkart_model.joblib` | 7860 |
| `frontend/` | Streamlit web app for single-product and batch (CSV) forecasts | 8501 |

## Run in a GitHub Codespace (or any machine with Docker)

One command builds both images, starts both containers, waits until they are healthy, sets ports 7860 and 8501 to
Public (in a Codespace), and prints the public addresses:

```bash
bash deploy.sh
```

Re-run it after `git pull` to deploy updated files. The equivalent manual steps:

```bash
docker network create superkart-net

cd backend
docker build -t superkart-backend .
docker run -d --restart unless-stopped --name backend --network superkart-net -p 7860:7860 superkart-backend

cd ../frontend
docker build -t superkart-frontend .
docker run -d --restart unless-stopped --name frontend --network superkart-net -p 8501:8501 superkart-frontend

docker ps    # both containers should report "(healthy)" after about 30 seconds
```

In a Codespace, ports 7860 and 8501 must be **Public** (`deploy.sh` does this; otherwise use the PORTS tab), then open the 8501 address for the web app.
The frontend reaches the backend by its container name (`http://backend:7860`) on the shared network.

## API

| Endpoint | Request | Response |
|:---|:---|:---|
| `GET /` | - | Status, input schema, training ranges and stores |
| `POST /v1/predict` | JSON object with the 10 features | `{"Sales": ..., "warnings": [...]}` |
| `POST /v1/predictbatch` | CSV file in form field `file` | `{"predictions": {"0": ..., ...}, "rows": n, "warnings": [...]}` |

Features: `Product_Weight, Product_Sugar_Content, Product_Allocated_Area, Product_MRP, Store_Size, Store_Location_City_Type, Store_Type, Product_Id_char, Store_Age_Years, Product_Type_Category`

Invalid input is rejected (HTTP 400, with every problem listed). Inputs the model has not seen in training are forecast and
flagged in `warnings`: unseen categories, numbers outside the training range, and store profiles that match none of the
four training stores (`backend/training_profile.json`).

## Stop and clean up

```bash
docker stop frontend backend && docker rm frontend backend && docker network rm superkart-net
```
