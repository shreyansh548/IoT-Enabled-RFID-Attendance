# RFID-Based Smart Attendance System

A prototype attendance system that reads RFID card IDs through a microcontroller, logs student entry/exit events, calculates session duration, synchronizes records with Google Sheets, and provides a Flask dashboard. Optional integrations send unknown-card alerts through UltraMsg and email daily CSV reports.

> **Privacy and security:** This repository intentionally excludes live attendance logs, credentials, and real student information. The included CSV contains synthetic demo records. Do not publish personal attendance data or secret keys.

## Features

- RFID UID-based student identification through serial input
- Entry/exit toggling and session-duration calculation
- Local CSV attendance log
- Google Sheets daily attendance and duration summaries
- Optional email reports and WhatsApp alerts for unknown cards
- Flask dashboard with total, present, exited, and attendance-history views
- Authenticated dashboard routes and CSRF protection for state-changing forms

## Architecture

1. The RFID reader scans a card and the microcontroller emits a serial line containing the UID and, when available, student details.
2. `script_py.py` reads the serial port and determines whether the scan is an entry or exit.
3. Attendance events are appended to `attendance.csv` and the configured Google spreadsheet.
4. On the teacher-card exit event, daily Google Sheets tabs are exported to CSV backups and optionally emailed.
5. `app.py` serves the dashboard from the local attendance CSV.

The actual microcontroller firmware was not included in the supplied archive. See [`firmware/README.md`](firmware/README.md) for what to add.

## Requirements

- Python 3.10 or newer
- RFID reader and microcontroller that emit the expected serial message format
- Google Sheets spreadsheet and a Google service-account credential file (optional only if you remove/disable the Sheets integration)
- Optional Gmail SMTP app password and UltraMsg credentials for notifications

## Setup

### 1. Create a virtual environment

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and replace all example values. Use a strong, unique `FLASK_SECRET_KEY`, a strong dashboard username/password, your serial port, and your teacher-card UID.

```powershell
# Windows PowerShell
Copy-Item .env.example .env
```

Do not commit `.env`. The dashboard will not accept logins until `DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD` are configured.

### 3. Configure Google Sheets

- Create or select a Google Cloud service account with only the permissions the project needs.
- Download its JSON key to `credentials/service-account.json` (or configure `GOOGLE_CREDENTIALS` to point to another local path).
- Share the target Google spreadsheet with the service account's email address.
- Keep the credential JSON out of Git. If a key was ever committed or shared, revoke it and create a replacement.

### 4. Run the dashboard

```bash
python app.py
```

Open `http://127.0.0.1:5000` and sign in using the values configured in `.env`.

### 5. Run the RFID reader

Connect the board, verify its COM/serial port, then run:

```bash
python script_py.py
```

The script expects lines similar to:

```text
UID: DEMOUID01 | Name: Demo Student 01 | RegNo: DEMO0001
```

Adapt the parsing logic if your firmware emits a different format. Keep the dashboard and reader script pointed at the same `ATTENDANCE_CSV` path if you want the dashboard to show the latest events.

## Configuration reference

| Variable | Purpose |
|---|---|
| `FLASK_SECRET_KEY` | Flask session signing key |
| `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD` | Dashboard login credentials |
| `SERIAL_PORT`, `BAUD_RATE` | Microcontroller serial connection |
| `TEACHER_UID` | UID used to detect teacher entry/exit |
| `GOOGLE_SHEET_NAME` | Spreadsheet title |
| `GOOGLE_CREDENTIALS` | Local path to service-account JSON |
| `SENDER_EMAIL`, `SENDER_PASSWORD`, `TEACHER_EMAIL` | Optional email reporting |
| `ULTRAMSG_TOKEN`, `ULTRAMSG_INSTANCE_ID`, `WHATSAPP_TEACHER_NUMBER` | Optional WhatsApp alerts |
| `ATTENDANCE_CSV` | Local attendance CSV path |
| `BACKUP_DIR` | Destination for generated daily backups |

## Data and backups

- `data/sample_attendance.csv` contains synthetic sample records only.
- Live `attendance.csv` is ignored by Git.
- Files under `backups/` are ignored by Git, except `.gitkeep`.
- Backups may contain personal data; store them securely and apply your institution's retention policy.

## Security notes

- Never commit `.env`, Google service-account keys, email passwords, messaging tokens, or live attendance records.
- The dashboard binds to `127.0.0.1` by default and debug mode is disabled. Do not expose it directly to the internet without a proper production deployment, HTTPS, and additional security review.
- The dashboard's clear action is an authenticated POST request with CSRF validation; it permanently clears the configured CSV file. Back up data before using it.
- RFID UIDs are identifiers, not strong authentication secrets. A copied card may be cloned; use additional controls if this is used beyond a prototype.

## Limitations

- The student entry-time dictionary is in memory; restarting the reader script loses currently open sessions.
- The system expects one scan to toggle entry/exit for each student. Adapt this if you need multiple readers, anti-passback logic, or recovery after a restart.
- The browser dashboard uses Chart.js from a CDN and therefore needs network access for the chart library.

## License

No license has been selected. Add a license only if you are comfortable granting others the permissions it provides.
