# main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Optional
import os
import requests
from requests import Response

# Load credentials from .env
load_dotenv()

app = FastAPI(title="Uber FastAPI Bridge", version="1.0")

# Environment variables
UBER_ACCESS_TOKEN = os.getenv("UBER_ACCESS_TOKEN")
UBER_BASE_URL = os.getenv("UBER_BASE_URL", "https://sandbox-api.uber.com/v1.2")

# Utility: Headers for Uber API
def uber_headers():
    if not UBER_ACCESS_TOKEN:
        raise HTTPException(status_code=500, detail="Missing Uber access token in environment.")
    return {
        "Authorization": f"Bearer {UBER_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

# Data model for ride requests
class RideRequest(BaseModel):
    start_latitude: float
    start_longitude: float
    end_latitude: float
    end_longitude: float
    product_id: Optional[str] = None


@app.get("/")
def root():
    return {"message": "✅ Uber FastAPI Bridge is running"}


@app.get("/products")
def list_products(lat: float, lon: float):
    """
    Lists available Uber ride products at a given location.
    """
    url = f"{UBER_BASE_URL}/products?latitude={lat}&longitude={lon}"
    response = requests.get(url, headers=uber_headers())
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@app.post("/request_ride")
def request_ride(ride: RideRequest):
    """
    Request a ride from Uber API (Sandbox or Production).
    """
    if not ride.product_id:
        raise HTTPException(status_code=400, detail="Missing product_id. Use /products to fetch available ride types first.")

    payload = {
        "product_id": ride.product_id,
        "start_latitude": ride.start_latitude,
        "start_longitude": ride.start_longitude,
        "end_latitude": ride.end_latitude,
        "end_longitude": ride.end_longitude
    }

    url = f"{UBER_BASE_URL}/requests"
    response = requests.post(url, headers=uber_headers(), json=payload)

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@app.post("/request_ride_sandbox")
def request_ride_sandbox(ride: RideRequest):
    """
    Create a sandbox ride request and immediately advance it to `accepted`.
    This uses the Uber Sandbox endpoints so no real ride is created.
    """
    if not ride.product_id:
        raise HTTPException(status_code=400, detail="Missing product_id. Use /products to fetch available ride types first.")

    payload = {
        "product_id": ride.product_id,
        "start_latitude": ride.start_latitude,
        "start_longitude": ride.start_longitude,
        "end_latitude": ride.end_latitude,
        "end_longitude": ride.end_longitude
    }

    # Step 1: Create the sandbox request
    create_url = f"{UBER_BASE_URL}/requests"
    try:
        create_resp: Response = requests.post(create_url, headers=uber_headers(), json=payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to contact Uber API: {e}")

    if create_resp.status_code >= 400:
        raise HTTPException(status_code=create_resp.status_code, detail=create_resp.text)

    create_data = create_resp.json()
    request_id = create_data.get("request_id")

    if not request_id:
        # Unexpected — return the create response
        return {"created": create_data}

    # Step 2: Advance the sandbox request to 'accepted'
    sandbox_url = f"{UBER_BASE_URL}/sandbox/requests/{request_id}"
    try:
        sandbox_resp = requests.put(sandbox_url, headers=uber_headers(), json={"status": "accepted"})
    except Exception as e:
        # Return created request but indicate the sandbox advance failed
        return {"created": create_data, "sandbox_advance_error": str(e)}

    # The sandbox advance returns 204 No Content on success
    if sandbox_resp.status_code not in (200, 204):
        return {"created": create_data, "sandbox_advance_status": sandbox_resp.status_code, "sandbox_advance_body": sandbox_resp.text}

    return {"created": create_data, "sandbox_advance": "accepted"}


@app.get("/ride_status/{request_id}")
def ride_status(request_id: str):
    """
    Check the status of an existing Uber ride request.
    """
    url = f"{UBER_BASE_URL}/requests/{request_id}"
    response = requests.get(url, headers=uber_headers())
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()
