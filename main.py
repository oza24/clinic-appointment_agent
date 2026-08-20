import json
import os
from fastapi import FastAPI, HTTPException
from google.oauth2.service_account import Credentials
import gspread
from pydantic import BaseModel
from datetime import datetime

app = FastAPI(title="Clinic Appointment Booking API")


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
                creds_dict["private_key"] = (
                    creds_dict["private_key"].replace("\\n", "\n")
                )

            creds = Credentials.from_service_account_info(
                creds_dict,
                scopes=SCOPE
            )

        else:
            creds = Credentials.from_service_account_file(
                "credentials.json",
                scopes=SCOPE
            )

        client = gspread.authorize(creds)

        sheet = client.open("Clinic_Appointments").sheet1

        print("[SHEETS] Connection successful!", flush=True)

        return sheet

    except Exception as e:
        print(
            f"[SHEETS ERROR] {str(e)}",
            flush=True
        )
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
    def coerce_phone_to_string(cls, v):
        # Convert integers or floats from Sarvam to clean string
        return str(v).strip()

    @field_validator("name", "date", "time", mode="before")
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
        "service": "Clinic Appointment Booking API"
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
async def health():

    return {
        "status": "healthy"
    }


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

        print(
            "[ERROR] Google Sheets connection failed",
            flush=True
        )

        raise HTTPException(
            status_code=500,
            detail="Google Sheets connection failed"
        )


    try:

        # ====================================================
        # READ EXISTING RECORDS
        # ====================================================

        print(
            "[BOOKING] Reading existing appointments...",
            flush=True
        )

        records = sheet.get_all_records()

        print(
            f"[BOOKING] Existing records: {len(records)}",
            flush=True
        )


        # ====================================================
        # CHECK DOUBLE BOOKING
        # ====================================================

        for row in records:

            existing_date = str(
                row.get("Date", "")
            ).strip()

            existing_time = str(
                row.get("Time", "")
            ).strip().lower()

            requested_date = data.date.strip()

            requested_time = data.time.strip().lower()


            if (
                existing_date == requested_date
                and existing_time == requested_time
            ):

                print(
                    "[BOOKING] SLOT ALREADY BOOKED",
                    flush=True
                )

                return {
                    "success": False,
                    "booking_status": "slot_unavailable",
                    "message": (
                        f"Sorry, the slot on "
                        f"{data.date} at {data.time} "
                        f"is already booked."
                    )
                }


        # ====================================================
        # TOKEN
        # ====================================================

        same_day_bookings = [

            row
            for row in records
            if str(row.get("Date", "")).strip()
            == data.date.strip()

        ]

        token_number = len(same_day_bookings) + 1


        print(
            f"[BOOKING] Generated token: {token_number}",
            flush=True
        )


        # ====================================================
        # APPEND
        # ====================================================

        print(
            "[BOOKING] Adding appointment to Google Sheet...",
            flush=True
        )

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


        print(
            "[BOOKING] Appointment successfully added!",
            flush=True
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
                f"Appointment successfully booked for "
                f"{data.name} on {data.date} at "
                f"{data.time}. "
                f"Your token number is "
                f"{token_number}."
            )
        }


        print(
            "[BOOKING] Returning successful response",
            flush=True
        )

        print(response, flush=True)

        return response


    except HTTPException:
        raise


    except Exception as e:

        print(
            f"[BOOKING ERROR] {str(e)}",
            flush=True
        )

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )