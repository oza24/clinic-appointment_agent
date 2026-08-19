import json
import os
from fastapi import FastAPI, HTTPException
from google.oauth2.service_account import Credentials
import gspread
from pydantic import BaseModel

app = FastAPI(title="Clinic Appointment Booking Webhook")

# --- GOOGLE SHEETS SETUP ---
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_google_sheet():
    """Helper to authenticate and fetch the sheet object."""
    try:
        env_creds = os.getenv("GOOGLE_CREDENTIALS_JSON")

        if env_creds:
            creds_dict = json.loads(env_creds)
            # Fix escaped newlines in private_key if present
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace(
                    "\\n", "\n"
                )
            creds = Credentials.from_service_account_info(
                creds_dict, scopes=SCOPE
            )
        else:
            creds = Credentials.from_service_account_file(
                "credentials.json", scopes=SCOPE
            )

        client = gspread.authorize(creds)
        return client.open("Clinic_Appointments").sheet1
    except Exception as e:
        print(f"Error connecting to Google Sheets: {e}")
        return None


# Global sheet reference
SHEET = get_google_sheet()


# --- DATA SCHEMA ---
class BookingPayload(BaseModel):
    name: str
    phone: str
    date: str  # Format: YYYY-MM-DD
    time: str  # Format: e.g., "10:00 AM"


# --- API ENDPOINT ---
@app.post("/api/book-appointment")
async def book_appointment(data: BookingPayload):
    global SHEET
    if not SHEET:
        SHEET = get_google_sheet()
        if not SHEET:
            raise HTTPException(
                status_code=500,
                detail="Google Sheets connection is not initialized. Check server credentials.",
            )

    try:
        records = SHEET.get_all_records()

        # 1. Prevent Double Booking
        for row in records:
            if (
                str(row.get("Date")) == data.date
                and str(row.get("Time")).strip().lower()
                == data.time.strip().lower()
            ):
                return {
                    "success": False,
                    "message": f"Sorry, the slot on {data.date} at {data.time} is already booked. Please choose a different time slot.",
                }

        # 2. Calculate Daily Token Number
        same_day_bookings = [
            r for r in records if str(r.get("Date")) == data.date
        ]
        token_number = len(same_day_bookings) + 1

        # 3. Append to Google Sheets
        SHEET.append_row(
            [
                data.date,
                data.time,
                data.name,
                data.phone,
                token_number,
                "Confirmed",
            ]
        )

        return {
            "success": True,
            "token_number": token_number,
            "message": f"Appointment successfully booked for {data.name} on {data.date} at {data.time}. Assigned queue token number is {token_number}.",
        }

    except Exception as e:
        print(f"Error executing booking: {e}")
        raise HTTPException(
            status_code=500, detail=f"Internal Server Error: {str(e)}"
        )


# Health Check Route
@app.get("/")
async def root():
    return {"status": "Backend server is running!"}