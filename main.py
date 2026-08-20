# import json
# import os
# from fastapi import FastAPI, HTTPException
# from google.oauth2.service_account import Credentials
# import gspread
# from pydantic import BaseModel

# app = FastAPI(title="Clinic Appointment Booking Webhook")

# # --- GOOGLE SHEETS SETUP ---
# SCOPE = [
#     "https://www.googleapis.com/auth/spreadsheets",
#     "https://www.googleapis.com/auth/drive",
# ]


# def get_google_sheet():
#     """Helper to authenticate and fetch the sheet object."""
#     try:
#         env_creds = os.getenv("GOOGLE_CREDENTIALS_JSON")

#         if env_creds:
#             creds_dict = json.loads(env_creds)
#             # Fix escaped newlines in private_key if present
#             if "private_key" in creds_dict:
#                 creds_dict["private_key"] = creds_dict["private_key"].replace(
#                     "\\n", "\n"
#                 )
#             creds = Credentials.from_service_account_info(
#                 creds_dict, scopes=SCOPE
#             )
#         else:
#             creds = Credentials.from_service_account_file(
#                 "credentials.json", scopes=SCOPE
#             )

#         client = gspread.authorize(creds)
#         return client.open("Clinic_Appointments").sheet1
#     except Exception as e:
#         print(f"Error connecting to Google Sheets: {e}")
#         return None


# # Global sheet reference
# SHEET = get_google_sheet()


# # --- DATA SCHEMA ---
# class BookingPayload(BaseModel):
#     name: str
#     phone: str
#     date: str  # Format: YYYY-MM-DD
#     time: str  # Format: e.g., "10:00 AM"


# # --- API ENDPOINT ---
# @app.post("/api/book-appointment")
# async def book_appointment(data: BookingPayload):
#     global SHEET
#     if not SHEET:
#         SHEET = get_google_sheet()
#         if not SHEET:
#             raise HTTPException(
#                 status_code=500,
#                 detail="Google Sheets connection is not initialized. Check server credentials.",
#             )

#     try:
#         records = SHEET.get_all_records()

#         # 1. Prevent Double Booking
#         for row in records:
#             if (
#                 str(row.get("Date")) == data.date
#                 and str(row.get("Time")).strip().lower()
#                 == data.time.strip().lower()
#             ):
#                 return {
#                     "success": False,
#                     "message": f"Sorry, the slot on {data.date} at {data.time} is already booked. Please choose a different time slot.",
#                 }

#         # 2. Calculate Daily Token Number
#         same_day_bookings = [
#             r for r in records if str(r.get("Date")) == data.date
#         ]
#         token_number = len(same_day_bookings) + 1

#         # 3. Append to Google Sheets
#         SHEET.append_row(
#             [
#                 data.date,
#                 data.time,
#                 data.name,
#                 data.phone,
#                 token_number,
#                 "Confirmed",
#             ]
#         )

#         return {
#             "success": True,
#             "token_number": token_number,
#             "message": f"Appointment successfully booked for {data.name} on {data.date} at {data.time}. Assigned queue token number is {token_number}.",
#         }

#     except Exception as e:
#         print(f"Error executing booking: {e}")
#         raise HTTPException(
#             status_code=500, detail=f"Internal Server Error: {str(e)}"
#         )


# # Health Check Route
# @app.get("/")
# async def root():
#     return {"status": "Backend server is running!"}




import json
import os
import logging
from datetime import datetime

import gspread
from fastapi import FastAPI, HTTPException
from google.oauth2.service_account import Credentials
from pydantic import BaseModel, Field


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="Clinic Appointment Booking API",
    version="1.0.0"
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("clinic-booking")


# ============================================================
# GOOGLE SHEETS
# ============================================================

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def get_google_sheet():
    """
    Connect to Google Sheets and return the first worksheet.
    """

    try:

        env_creds = os.getenv("GOOGLE_CREDENTIALS_JSON")

        if env_creds:

            creds_dict = json.loads(env_creds)

            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict[
                    "private_key"
                ].replace("\\n", "\n")

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

        spreadsheet = client.open("Clinic_Appointments")

        worksheet = spreadsheet.sheet1

        logger.info("Google Sheets connection successful")

        return worksheet

    except Exception as e:

        logger.exception(
            f"Google Sheets connection failed: {e}"
        )

        return None


# ============================================================
# REQUEST MODEL
# ============================================================

class BookingPayload(BaseModel):

    name: str = Field(
        ...,
        min_length=2,
        description="Patient full name"
    )

    phone: str = Field(
        ...,
        min_length=10,
        description="Patient phone number"
    )

    date: str = Field(
        ...,
        description="Appointment date in YYYY-MM-DD format"
    )

    time: str = Field(
        ...,
        description="Appointment time such as 10:00 AM"
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/")
async def root():

    return {
        "status": "Backend server is running!",
        "service": "Clinic Appointment Booking API"
    }


@app.get("/health")
async def health():

    sheet = get_google_sheet()

    return {
        "status": "healthy",
        "google_sheets": "connected" if sheet else "disconnected"
    }


# ============================================================
# BOOK APPOINTMENT
# ============================================================

@app.post("/api/book-appointment")
async def book_appointment(data: BookingPayload):

    logger.info("======================================")
    logger.info("BOOKING REQUEST RECEIVED")
    logger.info(f"Name: {data.name}")
    logger.info(f"Phone: {data.phone}")
    logger.info(f"Date: {data.date}")
    logger.info(f"Time: {data.time}")
    logger.info("======================================")


    # --------------------------------------------------------
    # Validate date
    # --------------------------------------------------------

    try:

        datetime.strptime(
            data.date,
            "%Y-%m-%d"
        )

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD."
        )


    # --------------------------------------------------------
    # Get Google Sheet
    # --------------------------------------------------------

    sheet = get_google_sheet()

    if not sheet:

        logger.error(
            "Google Sheets connection unavailable"
        )

        raise HTTPException(
            status_code=503,
            detail="Appointment system temporarily unavailable."
        )


    try:

        # ----------------------------------------------------
        # Read existing appointments
        # ----------------------------------------------------

        records = sheet.get_all_records()

        logger.info(
            f"Existing appointments: {len(records)}"
        )


        # ----------------------------------------------------
        # Check duplicate slot
        # ----------------------------------------------------

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

                logger.info(
                    "Requested slot already booked"
                )

                return {
                    "success": False,
                    "booking_status": "slot_unavailable",
                    "message": (
                        f"The slot on {data.date} "
                        f"at {data.time} is already booked."
                    )
                }


        # ----------------------------------------------------
        # Generate token
        # ----------------------------------------------------

        same_day_bookings = [

            row

            for row in records

            if str(
                row.get("Date", "")
            ).strip() == data.date.strip()

        ]


        token_number = len(
            same_day_bookings
        ) + 1


        logger.info(
            f"Generated token: {token_number}"
        )


        # ----------------------------------------------------
        # Add appointment to sheet
        # ----------------------------------------------------

        sheet.append_row(
            [
                data.date,
                data.time,
                data.name,
                data.phone,
                token_number,
                "Confirmed"
            ]
        )


        logger.info(
            "Appointment successfully added to Google Sheet"
        )


        # ----------------------------------------------------
        # Success response
        # ----------------------------------------------------

        response = {

            "success": True,

            "booking_status": "confirmed",

            "token_number": token_number,

            "patient_name": data.name,

            "date": data.date,

            "time": data.time,

            "message": (
                f"Appointment successfully booked for "
                f"{data.name} on {data.date} at "
                f"{data.time}. "
                f"Token number is {token_number}."
            )
        }


        logger.info(
            f"BOOKING SUCCESS: {response}"
        )

        return response


    except HTTPException:

        raise


    except Exception as e:

        logger.exception(
            f"Booking operation failed: {e}"
        )

        raise HTTPException(
            status_code=500,
            detail="Unable to complete appointment booking."
        )