"""RFID serial reader and attendance logger.

Configure hardware and integrations through environment variables. Keep the
Google service-account JSON outside version control and point GOOGLE_CREDENTIALS
at its local path.
"""
from __future__ import annotations

import csv
import os
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
import smtplib

import gspread
import requests
import serial
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SERIAL_PORT = os.getenv("SERIAL_PORT", "COM13")
BAUD_RATE = int(os.getenv("BAUD_RATE", "115200"))
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "RFID")
GOOGLE_CREDENTIALS = Path(os.getenv("GOOGLE_CREDENTIALS", str(BASE_DIR / "credentials" / "service-account.json")))
TEACHER_UID = os.getenv("TEACHER_UID", "")
TEACHER_EMAIL = os.getenv("TEACHER_EMAIL", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "")
ULTRAMSG_TOKEN = os.getenv("ULTRAMSG_TOKEN", "")
ULTRAMSG_INSTANCE_ID = os.getenv("ULTRAMSG_INSTANCE_ID", "")
WHATSAPP_TEACHER_NUMBER = os.getenv("WHATSAPP_TEACHER_NUMBER", "")
CSV_FILE = Path(os.getenv("ATTENDANCE_CSV", str(BASE_DIR / "attendance.csv")))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", str(BASE_DIR / "backups")))
HEADERS = ["Timestamp", "Name", "RegNo", "UID", "Status", "Duration"]


def ensure_csv() -> None:
    CSV_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not CSV_FILE.exists():
        with CSV_FILE.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(HEADERS)


def log_to_csv(timestamp, name, reg_no, uid, status, duration=""):
    with CSV_FILE.open("a", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow([timestamp, name, reg_no, uid, status, duration])


def get_google_client():
    if not GOOGLE_CREDENTIALS.is_file():
        raise FileNotFoundError(
            f"Google service-account JSON not found at {GOOGLE_CREDENTIALS}. "
            "Create/download it locally and set GOOGLE_CREDENTIALS in .env."
        )
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_file(str(GOOGLE_CREDENTIALS), scopes=scopes)
    return gspread.authorize(credentials)


def send_email_with_attachments(files, sheet_date):
    if not all([SENDER_EMAIL, SENDER_PASSWORD, TEACHER_EMAIL]):
        print("Email not sent: configure SENDER_EMAIL, SENDER_PASSWORD and TEACHER_EMAIL in .env.")
        return
    message = EmailMessage()
    message["Subject"] = f"Attendance Report for {sheet_date}"
    message["From"] = SENDER_EMAIL
    message["To"] = TEACHER_EMAIL
    message.set_content("Attached are today's attendance records and summary.")
    for path in files:
        with open(path, "rb") as handle:
            message.add_attachment(handle.read(), maintype="text", subtype="csv", filename=Path(path).name)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
            smtp.send_message(message)
        print("Email sent successfully.")
    except Exception as exc:
        print(f"Email error: {exc}")


def send_whatsapp_alert(uid, timestamp):
    if not all([ULTRAMSG_TOKEN, ULTRAMSG_INSTANCE_ID, WHATSAPP_TEACHER_NUMBER]):
        print("WhatsApp alert skipped: configure the UltraMsg settings in .env.")
        return
    url = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE_ID}/messages/chat"
    payload = {
        "token": ULTRAMSG_TOKEN,
        "to": WHATSAPP_TEACHER_NUMBER,
        "body": f"Unknown RFID card detected. UID: {uid}; Time: {timestamp}",
    }
    try:
        response = requests.post(url, data=payload, timeout=15)
        response.raise_for_status()
        print("WhatsApp alert sent.")
    except requests.RequestException as exc:
        print(f"WhatsApp error: {exc}")


def get_or_create_worksheet(spreadsheet, title, headers):
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=title, rows="1000", cols=str(max(10, len(headers))))
        worksheet.append_row(headers)
        return worksheet


def write_backup(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def main():
    ensure_csv()  # Never truncate existing attendance history at startup.
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not TEACHER_UID:
        raise RuntimeError("TEACHER_UID is not configured in .env.")
    client = get_google_client()
    spreadsheet = client.open(GOOGLE_SHEET_NAME)

    entry_times = {}
    teacher_present = False
    print(f"Listening for RFID tags on {SERIAL_PORT} at {BAUD_RATE} baud...")
    with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
        while True:
            try:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line.startswith("UID: "):
                    continue
                uid = line.split("UID: ", 1)[1].split(" |", 1)[0].strip()
                name = line.split("Name: ", 1)[1].split(" |", 1)[0].strip() if "Name: " in line else "Unknown"
                reg_no = line.split("RegNo: ", 1)[1].split(" |", 1)[0].strip() if "RegNo: " in line else "Unknown"
                now = datetime.now()
                timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
                date_name = now.strftime("%Y-%m-%d")
                day_sheet = get_or_create_worksheet(spreadsheet, date_name,
                    ["Timestamp", "Name", "Reg No", "UID", "Status", "Duration (min)"])
                total_sheet = get_or_create_worksheet(spreadsheet, f"{date_name}_Total",
                    ["Name", "Reg No", "UID", "Total Time (min)"])

                if name == "Unknown" or reg_no == "Unknown":
                    send_whatsapp_alert(uid, timestamp)

                if uid == TEACHER_UID:
                    teacher_present = not teacher_present
                    status = "Entered" if teacher_present else "Exited"
                    day_sheet.append_row([timestamp, name, reg_no, uid, status, ""])
                    log_to_csv(timestamp, name, reg_no, uid, status)
                    if not teacher_present:
                        day_data = day_sheet.get_all_values()
                        total_data = total_sheet.get_all_values()
                        attendance_backup = BACKUP_DIR / f"Attendance_Log_{date_name}.csv"
                        duration_backup = BACKUP_DIR / f"Total_Duration_{date_name}.csv"
                        write_backup(day_data, attendance_backup)
                        write_backup(total_data, duration_backup)
                        send_email_with_attachments([attendance_backup, duration_backup], date_name)
                    continue

                if uid in entry_times:
                    entry_time = entry_times.pop(uid)
                    duration = round((now - entry_time).total_seconds() / 60, 2)
                    status = "Exited"
                    day_sheet.append_row([timestamp, name, reg_no, uid, status, duration])
                    log_to_csv(timestamp, name, reg_no, uid, status, duration)
                    records = total_sheet.get_all_records()
                    for row_index, record in enumerate(records, start=2):
                        if str(record.get("UID", "")).strip() == uid:
                            current = float(record.get("Total Time (min)") or 0)
                            total_sheet.update_cell(row_index, 4, round(current + duration, 2))
                            break
                    else:
                        total_sheet.append_row([name, reg_no, uid, duration])
                else:
                    entry_times[uid] = now
                    status = "Entered"
                    day_sheet.append_row([timestamp, name, reg_no, uid, status, ""])
                    log_to_csv(timestamp, name, reg_no, uid, status)
                print(f"Logged: {uid} | {name} | {reg_no} | {status} at {timestamp}")
            except KeyboardInterrupt:
                print("Stopping RFID reader.")
                break
            except Exception as exc:
                print(f"Processing error: {exc}")
                time.sleep(1)


if __name__ == "__main__":
    main()
