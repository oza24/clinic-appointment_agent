import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = FastAPI(title="Clinic Appointment Booking Webhook")

# --- GOOGLE SHEETS SETUP ---
# Initialize Google Sheets client using service account credentials
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

try:
    CREDS = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
    GSPREAD_CLIENT = gspread.authorize(CREDS)
    SHEET = GSPREAD_CLIENT.open("Clinic_Appointments").sheet1
    print("Successfully connected to Google Sheets!")
except Exception as e:
    print(f"Error connecting to Google Sheets: {e}")

# --- DATA SCHEMA ---
# Defines the JSON payload structure expected from Sarvam AI / MCP
class BookingPayload(BaseModel):
    name: str
    phone: str
    date: str  # Format: YYYY-MM-DD
    time: str  # Format: e.g., "10:00 AM"

# --- API ENDPOINT ---
@app.post("/api/book-appointment")
async def book_appointment(data: BookingPayload):
    try:
        # Fetch all existing records from the sheet
        records = SHEET.get_all_records()
        
        # 1. Prevent Double Booking for the same date and time slot
        for row in records:
            if str(row.get("Date")) == data.date and str(row.get("Time")).strip().lower() == data.time.strip().lower():
                return {
                    "success": False,
                    "message": f"Sorry, the slot on {data.date} at {data.time} is already booked. Please ask the caller to choose a different time slot."
                }
        
        # 2. Calculate the Daily Token Number
        # Counts existing appointments for the specified date and assigns the next number
        same_day_bookings = [r for r in records if str(r.get("Date")) == data.date]
        token_number = len(same_day_bookings) + 1
        
        # 3. Append the new appointment row into Google Sheets
        # Columns: Date | Time | Patient Name | Phone Number | Token Number | Status
        SHEET.append_row([
            data.date, 
            data.time, 
            data.name, 
            data.phone, 
            token_number, 
            "Confirmed"
        ])
        
        return {
            "success": True,
            "token_number": token_number,
            "message": f"Appointment successfully booked for {data.name} on {data.date} at {data.time}. Assigned queue token number is {token_number}."
        }
        
    except Exception as e:
        print(f"Error executing booking: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# Health Check Route
@app.get("/")
async def root():
    return {"status": "Backend server is running!"}