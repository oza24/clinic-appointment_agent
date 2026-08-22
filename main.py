import json
import os
from datetime import datetime
from fastapi import FastAPI, HTTPException
from google.oauth2.service_account import Credentials
import gspread
from pydantic import BaseModel, field_validator
import requests
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Clinic Appointment Booking API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows requests from any frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# EXOTEL SMS CONFIGURATION (Fetched from Render Env Variables)
# ============================================================
EXOTEL_ACCOUNT_SID = os.getenv("EXOTEL_ACCOUNT_SID")
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")
EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")


def send_exotel_sms(to_phone: str, patient_name: str, date: str, time: str, token: int):
    """Sends a transactional confirmation SMS using Exotel API."""
    if not all([EXOTEL_ACCOUNT_SID, EXOTEL_API_KEY, EXOTEL_API_TOKEN]):
        print(
            "[SMS WARNING] Exotel credentials missing in environment variables. Skipping SMS.",
            flush=True,
        )
        return

    try:
        # Sanitize phone number (removes +91, spaces, or dashes)
        clean_phone = (
            str(to_phone)
            .replace("+91", "")
            .replace("+", "")
            .replace(" ", "")
            .strip()
        )

        url = f"https://api.exotel.com/v1/Accounts/{EXOTEL_ACCOUNT_SID}/Sms/send.json"

        sms_body = (
            f"Dear {patient_name}, your appointment is confirmed for {date} at {time}. "
            f"Your Token No is #{token}. Thank you!"
        )

        payload = {
            "From": EXOTEL_ACCOUNT_SID,
            "To": clean_phone,
            "Body": sms_body,
        }

        print(f"[SMS] Sending confirmation SMS to {clean_phone}...", flush=True)

        response = requests.post(
            url,
            data=payload,
            auth=(EXOTEL_API_KEY, EXOTEL_API_TOKEN),
            timeout=5,
        )

        if response.status_code == 200:
            print(f"[SMS SUCCESS] Message delivered to {clean_phone}!", flush=True)
        else:
            print(
                f"[SMS ERROR] Status {response.status_code}: {response.text}",
                flush=True,
            )

    except Exception as e:
        print(f"[SMS EXCEPTION] Failed to send SMS: {str(e)}", flush=True)


# ============================================================
# GOOGLE SHEETS
# ============================================================

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_google_sheet():
    try:
        print("[SHEETS] Connecting to Google Sheets...", flush=True)

        env_creds = os.getenv("GOOGLE_CREDENTIALS_JSON")

        if env_creds:
            creds_dict = json.loads(env_creds)

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

        sheet = client.open("Clinic_Appointments").sheet1

        print("[SHEETS] Connection successful!", flush=True)

        return sheet

    except Exception as e:
        print(f"[SHEETS ERROR] {str(e)}", flush=True)
        return None


# ============================================================
# DATA MODEL
# ============================================================


class BookingPayload(BaseModel):
    name: str
    phone: str
    date: str
    time: str

    @field_validator("phone", mode="before")
    @classmethod
    def coerce_phone_to_string(cls, v):
        return str(v).strip()

    @field_validator("name", "date", "time", mode="before")
    @classmethod
    def clean_strings(cls, v):
        return str(v).strip() if v is not None else ""


# ============================================================
# ROOT
# ============================================================


@app.get("/")
async def root():
    print("[HEALTH] Root endpoint called", flush=True)

    return {
        "status": "Backend server is running!",
        "service": "Clinic Appointment Booking API",
    }


# ============================================================
# HEALTH
# ============================================================


@app.get("/health")
async def health():
    return {"status": "healthy"}

#============================================================
## Get all appointments 
#============================================================

# ============================================================
# GET ALL APPOINTMENTS (Cleaned Keys)
# ============================================================


@app.get("/api/appointments")
async def get_appointments():
    sheet = get_google_sheet()
    if not sheet:
        raise HTTPException(
            status_code=500, detail="Google Sheets connection failed"
        )
    try:
        raw_records = sheet.get_all_records()

        # Sanitize keys: strips whitespace and handles any header variations
        cleaned_records = []
        for row in raw_records:
            cleaned_row = {}
            for k, v in row.items():
                clean_key = str(k).strip()
                clean_val = str(v).strip() if v is not None else ""

                # Standardize keys for the frontend
                if clean_key in ["Patient Name", "Name", "Patient Name "]:
                    cleaned_row["name"] = clean_val
                elif clean_key in ["Phone Number", "Phone", "Phone Number "]:
                    cleaned_row["phone"] = clean_val
                elif clean_key in ["Token Number", "Token", "Token Number "]:
                    cleaned_row["token"] = clean_val
                elif clean_key in ["Date", "Date "]:
                    cleaned_row["date"] = clean_val
                elif clean_key in ["Time", "Time "]:
                    cleaned_row["time"] = clean_val
                elif clean_key in ["Status", "Status "]:
                    cleaned_row["status"] = clean_val
                else:
                    cleaned_row[clean_key.lower()] = clean_val

            cleaned_records.append(cleaned_row)

        return {"success": True, "data": cleaned_records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# ============================================================
# BOOK APPOINTMENT
# ============================================================


@app.post("/api/book-appointment")
async def book_appointment(data: BookingPayload):
    print("\n========================================", flush=True)
    print("🚨 BOOKING REQUEST RECEIVED", flush=True)
    print("========================================", flush=True)

    print(f"Name  : {data.name}", flush=True)
    print(f"Phone : {data.phone}", flush=True)
    print(f"Date  : {data.date}", flush=True)
    print(f"Time  : {data.time}", flush=True)

    print("========================================\n", flush=True)

    sheet = get_google_sheet()

    if not sheet:
        print("[ERROR] Google Sheets connection failed", flush=True)

        raise HTTPException(
            status_code=500, detail="Google Sheets connection failed"
        )

    try:
        # ====================================================
        # READ EXISTING RECORDS
        # ====================================================

        print("[BOOKING] Reading existing appointments...", flush=True)

        records = sheet.get_all_records()

        print(f"[BOOKING] Existing records: {len(records)}", flush=True)

        # ====================================================
        # CHECK DOUBLE BOOKING
        # ====================================================

        for row in records:
            existing_date = str(row.get("Date", "")).strip()

            existing_time = str(row.get("Time", "")).strip().lower()

            requested_date = data.date.strip()

            requested_time = data.time.strip().lower()

            if (
                existing_date == requested_date
                and existing_time == requested_time
            ):
                print("[BOOKING] SLOT ALREADY BOOKED", flush=True)

                return {
                    "success": False,
                    "booking_status": "slot_unavailable",
                    "message": (
                        f"Sorry, the slot on {data.date} at {data.time} is already booked."
                    ),
                }

        # ====================================================
        # TOKEN
        # ====================================================

        same_day_bookings = [
            row
            for row in records
            if str(row.get("Date", "")).strip() == data.date.strip()
        ]

        token_number = len(same_day_bookings) + 1

        print(f"[BOOKING] Generated token: {token_number}", flush=True)

        # ====================================================
        # APPEND
        # ====================================================

        print("[BOOKING] Adding appointment to Google Sheet...", flush=True)

        sheet.append_row(
            [
                data.date,
                data.time,
                data.name,
                data.phone,
                token_number,
                "Confirmed",
            ]
        )

        print("[BOOKING] Appointment successfully added!", flush=True)

        # ====================================================
        # SEND SMS CONFIRMATION
        # ====================================================

        send_exotel_sms(
            to_phone=data.phone,
            patient_name=data.name,
            date=data.date,
            time=data.time,
            token=token_number,
        )

        # ====================================================
        # RESPONSE
        # ====================================================

        response = {
            "success": True,
            "booking_status": "confirmed",
            "token_number": token_number,
            "name": data.name,
            "phone": data.phone,
            "date": data.date,
            "time": data.time,
            "message": (
                f"Appointment successfully booked for {data.name} on {data.date} at {data.time}. "
                f"Your token number is {token_number}."
            ),
        }

        print("[BOOKING] Returning successful response", flush=True)

        print(response, flush=True)

        return response

    except HTTPException:
        raise

    except Exception as e:
        print(f"[BOOKING ERROR] {str(e)}", flush=True)

        raise HTTPException(status_code=500, detail=str(e))