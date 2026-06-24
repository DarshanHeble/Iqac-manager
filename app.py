from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import os, random, string, json, urllib.request, urllib.error
# import smtplib  # SMTP fallback — kept for reference, replaced by Brevo
from datetime import datetime, timedelta
# from email.mime.text import MIMEText  # SMTP fallback — replaced by Brevo
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from io import BytesIO
import calendar
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables from .env file (override any existing env vars)
load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")

from routes.pdf import pdf_bp
app.register_blueprint(pdf_bp)

# Cloudinary configuration
import cloudinary
import cloudinary.uploader
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

def cloudinary_upload(file_obj, folder, public_id=None, resource_type="auto"):
    opts = {"folder": folder, "resource_type": resource_type, "access_mode": "public"}
    if public_id:
        opts["public_id"] = public_id
        opts["overwrite"] = True
    result = cloudinary.uploader.upload(file_obj, **opts)
    return result["secure_url"], result["public_id"]

def cloudinary_delete(public_id, resource_type="auto"):
    try:
        cloudinary.uploader.destroy(public_id, resource_type=resource_type)
    except Exception as e:
        print(f"Cloudinary delete error: {e}")

# Jinja filter: make Cloudinary URL open inline in browser instead of downloading
@app.template_filter('inline_url')
def inline_url(url):
    if url and 'cloudinary.com' in url and '/upload/' in url:
        return url.replace('/upload/', '/upload/fl_attachment:false/')
    return url

# Make datetime and timedelta available in all templates
app.jinja_env.globals['datetime'] = datetime
app.jinja_env.globals['timedelta'] = timedelta

# Add context processor for current year in footer
@app.context_processor
def inject_now():
    return {'now': datetime.now}

# ------------------ DATABASE CONFIGURATION (PostgreSQL) ------------------
from db import get_db_connection, get_cursor

# ------------------ EMAIL SETTINGS (Environment Variables) ------------------
# SMTP_EMAIL = os.getenv("SMTP_EMAIL")      # SMTP fallback — replaced by Brevo
# SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
# SMTP_SERVER = "smtp.gmail.com"
# SMTP_PORT = 587

# ------------------ AQAR COORDINATOR SETTINGS ------------------
def _parse_csv_env(key):
    val = os.getenv(key, "")
    return [v.strip() for v in val.split(",") if v.strip()] if val else []

AQAR_COORDINATOR_EMAILS = _parse_csv_env("AQAR_COORDINATOR_EMAILS")
AQAR_COORDINATOR_NAMES = _parse_csv_env("AQAR_COORDINATOR_NAMES")

def is_aqar_coordinator(user):
    """Check if a user should see the AQAR-aligned report based on their email."""
    email = (user.get("email") or "").strip().lower() if isinstance(user, dict) else (user["email"] or "").strip().lower()
    return email in [e.lower() for e in AQAR_COORDINATOR_EMAILS]

# ------------------ EMAIL REMINDER FUNCTIONS ------------------
def send_email(to_email, subject, body):
    """Send email via Brevo Web API"""
    brevo_api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("SENDER_EMAIL")
    if not brevo_api_key or not sender_email:
        raise Exception("BREVO_API_KEY and SENDER_EMAIL must be set in .env")

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": brevo_api_key,
        "content-type": "application/json"
    }
    payload = {
        "sender": {"name": "IQAC Admin", "email": sender_email},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = response.read()
            print(f"Brevo email sent successfully to {to_email}: {res_data}")
            return True
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8')
        print(f"HTTP Error sending Brevo email to {to_email}: {e.code} - {err_msg}")
        raise Exception(f"Brevo API error: {e.code} - {err_msg}")
    except Exception as e:
        print(f"Failed to send Brevo email to {to_email}: {str(e)}")
        raise e

    # --- SMTP fallback (disabled — replaced by Brevo) ---
    # SMTP_EMAIL = os.getenv("SMTP_EMAIL")
    # SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    # if not SMTP_EMAIL or not SMTP_PASSWORD:
    #     raise Exception("Neither BREVO_API_KEY nor SMTP credentials are set.")
    # from email.mime.text import MIMEText
    # import smtplib
    # msg = MIMEText(body, 'plain', 'utf-8')
    # msg['Subject'] = subject
    # msg['From'] = SMTP_EMAIL
    # msg['To'] = to_email
    # with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
    #     server.starttls()
    #     server.login(SMTP_EMAIL, SMTP_PASSWORD)
    #     server.send_message(msg)

def send_reminder_email(to_email, subject, body):
    """Send an email reminder"""
    try:
        return send_email(to_email, subject, body)
    except Exception as e:
        print(f"Failed to send email to {to_email}: {str(e)}")
        return False

def notify_admins_and_secretaries(username, reporting_month):
    """Notify all admins and secretaries about the uploaded report."""
    emails = []
    smtp_email = os.getenv("SMTP_EMAIL") or os.getenv("SENDER_EMAIL")
    if smtp_email:
        emails.append(smtp_email.strip())

    conn = get_db_connection()
    cursor = get_cursor(conn)
    try:
        cursor.execute("""
            SELECT email FROM users 
            WHERE LOWER(role) = 'admin' 
               OR LOWER(role) LIKE '%secretary%' 
               OR LOWER(designation) LIKE '%secretary%'
               OR LOWER(username) LIKE '%secretary%'
        """)
        for row in cursor.fetchall():
            email = (row.get("email") or "").strip()
            if email and email not in emails:
                emails.append(email)
    except Exception as e:
        print("Error fetching secretary/admin emails:", str(e))
    finally:
        conn.close()

    if not emails:
        print("No admin or secretary emails found to send notification.")
        return

    subject = f"Signed IQAC Monthly Report Uploaded - {username.title()} ({reporting_month})"
    body = (
        f"Hello,\n\n"
        f"IQAC Coordinator '{username.title()}' has uploaded the signed monthly report for the month '{reporting_month}'.\n\n"
        f"Please log in to the IQAC Portal to review and authorize this submission.\n\n"
        f"Regards,\n"
        f"IQAC System"
    )

    for email in emails:
        try:
            send_email(email, subject, body)
            print(f"Sent upload notification email to {email}")
        except Exception as ex:
            print(f"Failed to send email to {email}: {str(ex)}")

def notify_coordinator_of_rejection(username, reporting_month, remarks=""):
    """Notify the coordinator that corrections are requested on their report."""
    conn = get_db_connection()
    cursor = get_cursor(conn)
    email = None
    try:
        cursor.execute("SELECT email FROM users WHERE username = %s", (username,))
        row = cursor.fetchone()
        if row:
            email = row.get("email")
    except Exception as e:
        print("Error fetching coordinator email:", str(e))
    finally:
        conn.close()

    if not email:
        print(f"No email found for coordinator {username}")
        return

    subject = f"IQAC Monthly Report Correction Required - ({reporting_month})"
    body = (
        f"Hello {username.title()},\n\n"
        f"Your signed monthly report for the month '{reporting_month}' has been reviewed and correction has been requested.\n"
    )
    if remarks:
        body += f"\nRemarks / Reason for correction:\n\"{remarks}\"\n\n"
    body += (
        f"Your report draft has been unlocked. Please log in to the IQAC Portal, edit the report details, download the corrected PDF, sign it, and upload the signed PDF again.\n\n"
        f"Regards,\n"
        f"IQAC System"
    )
    try:
        send_email(email, subject, body)
        print(f"Sent rejection email to coordinator {email}")
    except Exception as ex:
        print(f"Failed to send email to {email}: {str(ex)}")

def get_nth_weekday_of_month(year, month, weekday, n):
    """Get the nth occurrence of a weekday in a month (0=Monday, 6=Sunday)"""
    first_day = datetime(year, month, 1)
    first_weekday = first_day.weekday()
    # Convert to weekday() format where Monday=0, Sunday=6
    days_to_add = (weekday - first_weekday) % 7
    nth_date = 1 + days_to_add + (n - 1) * 7
    return datetime(year, month, nth_date).date()

def is_working_day(date):
    """Check if a date is a working day (not Sunday or 3rd Saturday)"""
    weekday = date.weekday()  # Monday=0, Sunday=6
    
    # Sunday
    if weekday == 6:
        return False
    
    # Check if it's 3rd Saturday
    if weekday == 5:  # Saturday
        third_saturday = get_nth_weekday_of_month(date.year, date.month, 5, 3)
        if date == third_saturday:
            return False
    
    return True

def get_working_days_in_month(year, month):
    """Get all working days in a given month"""
    last_day = calendar.monthrange(year, month)[1]
    working_days = []
    
    for day in range(1, last_day + 1):
        date = datetime(year, month, day).date()
        if is_working_day(date):
            working_days.append(date)
    
    return working_days

def get_missing_entries(username, year, month):
    """Get list of working days without worklog entries for a user"""
    conn = get_db_connection()
    cursor = get_cursor(conn)
    
    # Get all worklog entries for the user in the specified month
    cursor.execute("""
        SELECT date FROM worklog 
        WHERE username=%s 
        AND EXTRACT(YEAR FROM date::date) = %s 
        AND EXTRACT(MONTH FROM date::date) = %s
    """, (username, year, month))
    
    filled_dates = {row['date'] for row in cursor.fetchall()}
    conn.close()
    
    # Get all working days in the month
    working_days = get_working_days_in_month(year, month)
    
    # Find missing entries (only for past dates)
    today = datetime.now().date()
    missing_dates = [d for d in working_days if d not in filled_dates and d <= today]
    
    return missing_dates

def send_reminder_email(to_email, subject, body):
    """Send an email reminder"""
    try:
        return send_email(to_email, subject, body)
    except Exception as e:
        print(f"Failed to send email to {to_email}: {str(e)}")
        return False

def format_dates_by_month(dates):
    """Format dates grouped by month. Example: 'Feb - 2, 3, 5' / 'Mar - 1, 2'"""
    from collections import defaultdict
    by_month = defaultdict(list)
    
    for date in dates:
        month_str = date.strftime('%b')
        day = date.day
        by_month[month_str].append(day)
    
    formatted_parts = []
    for date in sorted(dates):
        month_str = date.strftime('%b')
        if month_str not in [p.split(' - ')[0] for p in formatted_parts]:
            days = sorted(by_month[month_str])
            days_str = ', '.join(str(d) for d in days)
            formatted_parts.append(f"{month_str} - {days_str}")
    
    return ' / '.join(formatted_parts)

def send_29th_reminder():
    """Send reminder on 29th of month about missing entries"""
    conn = get_db_connection()
    cursor = get_cursor(conn)
    
    # Get all Employee/Intern users (exclude Admin and Coordinators)
    cursor.execute("SELECT username, email FROM users WHERE LOWER(role) NOT IN ('admin', 'school iqac coordinator', 'campus iqac coordinator')")
    users = cursor.fetchall()
    conn.close()

    today = datetime.now().date()
    current_year = today.year
    current_month = today.month
    
    for user in users:
        username = user['username']
        email = user['email']
        
        missing_dates = get_missing_entries(username, current_year, current_month)
        
        if missing_dates:
            # Format missing dates grouped by month (Feb - 2, 3, 5)
            sorted_dates = sorted(missing_dates)
            dates_list = format_dates_by_month(sorted_dates)
            # Get deadline date (2nd of next month)
            if current_month == 12:
                deadline_date = datetime(current_year + 1, 1, 2).date()
            else:
                deadline_date = datetime(current_year, current_month + 1, 2).date()
            deadline_str = deadline_date.strftime('%d-%m-%Y')
            
            subject = f"IQAC Worklog Reminder - Missing Entries"
            body = f"""Dear {username},

This is a kind reminder to complete and submit your work logs for the dates:

{dates_list}

The final date to submit your log is {deadline_str}. Please log in to the portal and complete the submission before the deadline.

If you have already submitted the work logs kindly disregard this email.

---
This is an auto-generated email. Please do not reply to this message.
"""
            send_reminder_email(email, subject, body)
    
    return f"29th reminder sent to {len(users)} users"

def send_1st_deadline_reminder():
    """Send final reminder on 1st of month - deadline is today midnight"""
    conn = get_db_connection()
    cursor = get_cursor(conn)
    
    # Get all Employee/Intern users (exclude Admin and Coordinators)
    cursor.execute("SELECT username, email FROM users WHERE LOWER(role) NOT IN ('admin', 'school iqac coordinator', 'campus iqac coordinator')")
    users = cursor.fetchall()
    conn.close()

    today = datetime.now().date()
    # Previous month
    if today.month == 1:
        prev_month = 12
        prev_year = today.year - 1
    else:
        prev_month = today.month - 1
        prev_year = today.year
    
    for user in users:
        username = user['username']
        email = user['email']
        
        missing_dates = get_missing_entries(username, prev_year, prev_month)
        
        if missing_dates:
            # Format missing dates grouped by month (Feb - 2, 3, 5)
            sorted_dates = sorted(missing_dates)
            dates_list = format_dates_by_month(sorted_dates)
            deadline_str = today.strftime('%d-%m-%Y')
            
            subject = f"URGENT: IQAC Worklog Submission Deadline - TODAY"
            body = f"""Dear {username},

This is a kind reminder to complete and submit your work logs for the dates:

{dates_list}

The final date to submit your log is {deadline_str} (TODAY). Please log in to the portal and complete the submission before the deadline.

If you have already submitted the work logs kindly disregard this email.

---
This is an auto-generated email. Please do not reply to this message.
"""
            send_reminder_email(email, subject, body)
    
    return f"1st deadline reminder sent to {len(users)} users"

# ------------------ GEMINI AI SETTINGS ------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ai_client = None
if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
    try:
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Warning: Failed to initialize Gemini Client: {e}")

def build_ai_summary_prompt(logs, selected_user, filter_mode, from_date, to_date, selected_month, selected_academic_year, category_filter):
    period_label = "Custom Date Range"
    period_value = f"{from_date or '—'} to {to_date or '—'}"
    if filter_mode == "month":
        period_label = "Month-wise"
        period_value = selected_month or "—"
    elif filter_mode == "academic_year":
        period_label = "Academic Year"
        period_value = selected_academic_year or "—"

    lines = [
        "You are an assistant summarizing worklog entries for an IQAC report.",
        "Generate a summary with ONLY these two sections in this exact format:",
        "",
        "1. Key Activities",
        "List the main activities completed during this period in a single paragraph.",
        "",
        "2. Major Focus Areas",
        "Organize by category. For each category that has entries, write a brief description of the work done.",
        "Format as: 'Category Name: description of activities'",
        "Categories may include: Documentation and Audits, Rankings, Publications, Training and Development, Strategic Initiatives, Others, Holiday.",
        "IMPORTANT: Do NOT include or mention 'Leave' entries in the summary.",
        "",
        "Do not include an introductory paragraph, conclusion, or patterns/trends section.",
        "Do not use markdown, bullets, or asterisks. Use plain text with section headings.",
        "Write in a formal, official report tone.",
        "",
        f"User: {selected_user or '—'}",
        f"Category Filter: {category_filter or 'All'}",
        f"Report Type: {period_label}",
        f"Period: {period_value}",
        f"Total Entries: {len(logs)}",
        "",
        "Entries:"
    ]

    if selected_user == "All":
        grouped = {}
        for log in logs:
            uname = log.get("username")
            grouped.setdefault(uname, []).append(log)
        for uname, entries in grouped.items():
            lines.append(f"User: {uname}")
            for log in entries:
                date = log.get("date") or "—"
                tasks_dict = log.get("tasks_dict") or {}
                if tasks_dict:
                    for cat, task in tasks_dict.items():
                        # Skip Leave entries
                        if cat.lower() == "leave":
                            continue
                        lines.append(f"- {date} | {cat}: {task}")
                else:
                    lines.append(f"- {date} | No tasks recorded")
            lines.append("")
    else:
        for log in logs:
            date = log.get("date") or "—"
            tasks_dict = log.get("tasks_dict") or {}
            if tasks_dict:
                for cat, task in tasks_dict.items():
                    # Skip Leave entries
                    if cat.lower() == "leave":
                        continue
                    lines.append(f"- {date} | {cat}: {task}")
            else:
                lines.append(f"- {date} | No tasks recorded")

    return "\n".join(lines)

# ------------------ APP SETTINGS HELPER ------------------
def get_submission_window():
    """Return (open_day, close_day) from app_settings."""
    try:
        conn = get_db_connection()
        cursor = get_cursor(conn)
        cursor.execute("SELECT key, value FROM app_settings WHERE key IN ('submission_open_day', 'submission_close_day')")
        rows = {r['key']: int(r['value']) for r in cursor.fetchall()}
        conn.close()
        return rows.get('submission_open_day', 1), rows.get('submission_close_day', 5)
    except Exception:
        return 1, 5

def check_submission_window():
    """
    Returns (is_open, reporting_month_str, open_day, close_day, window_msg).
    The window for last month's report opens on open_day and closes on close_day
    of the current month.
    """
    open_day, close_day = get_submission_window()
    today = datetime.now().date()
    current_day = today.day

    # The report being submitted is always for the previous month
    if today.month == 1:
        report_year, report_month = today.year - 1, 12
    else:
        report_year, report_month = today.year, today.month - 1

    reporting_month_str = f"{report_year}-{report_month:02d}"
    month_name = datetime(report_year, report_month, 1).strftime("%m-%Y")

    is_open = open_day <= current_day <= close_day

    if is_open:
        close_date = today.replace(day=close_day).strftime("%d-%m-%Y")
        window_msg = f"Submission window for {month_name} is open until {close_date}."
    elif current_day < open_day:
        open_date = today.replace(day=open_day).strftime("%d-%m-%Y")
        window_msg = f"Submission window for {month_name} opens on {open_date}."
    else:
        # Past the close day — next window is next month
        if today.month == 12:
            next_open = datetime(today.year + 1, 1, open_day).strftime("%d-%m-%Y")
        else:
            next_open = datetime(today.year, today.month + 1, open_day).strftime("%d-%m-%Y")
        close_date = today.replace(day=close_day).strftime("%d-%m-%Y")
        window_msg = (f"Submission window for {month_name} closed on {close_date}. "
                      f"Next window opens {next_open}.")

    return is_open, reporting_month_str, open_day, close_day, window_msg

# ------------------ DISABLE CACHING ------------------
@app.after_request
def disable_cache(resp):
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

# ------------------ INIT DATABASE (PostgreSQL) ------------------
def init_postgres():
    """Initialize PostgreSQL database with tables and default admin"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            emp_id VARCHAR(50),
            email VARCHAR(255),
            gender VARCHAR(20),
            designation VARCHAR(255),
            department VARCHAR(255),
            role VARCHAR(50),
            full_name VARCHAR(255)
        )
    """)

    # Create worklog table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worklog (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            date VARCHAR(20),
            status VARCHAR(50),
            category TEXT,
            task TEXT,
            attachment TEXT
        )
    """)
    cursor.execute("ALTER TABLE worklog ADD COLUMN IF NOT EXISTS attachment TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255)")

    # Create signed_reports table for IQAC Coordinator uploaded reports
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signed_reports (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            reporting_month VARCHAR(20),
            uploaded_file_path VARCHAR(500),
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20) DEFAULT 'pending'
        )
    """)
    cursor.execute("ALTER TABLE signed_reports ADD COLUMN IF NOT EXISTS remarks TEXT")
    cursor.execute("ALTER TABLE signed_reports ALTER COLUMN status TYPE VARCHAR(50)")
    cursor.execute("ALTER TABLE signed_reports ADD COLUMN IF NOT EXISTS cloudinary_public_id VARCHAR(500)")

    # Create workshop_attachment_files table for Cloudinary-stored workshop files
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workshop_attachment_files (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            reporting_month VARCHAR(20) NOT NULL,
            workshop_index INTEGER NOT NULL,
            filename VARCHAR(500),
            cloudinary_url VARCHAR(1000),
            cloudinary_public_id VARCHAR(500),
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (username, reporting_month, workshop_index)
        )
    """)

    # Create app_settings table for configurable options
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key VARCHAR(100) PRIMARY KEY,
            value VARCHAR(255)
        )
    """)
    # Default submission window: open on 1st, close on 5th of each month
    cursor.execute("INSERT INTO app_settings (key, value) VALUES ('submission_open_day', '1') ON CONFLICT (key) DO NOTHING")
    cursor.execute("INSERT INTO app_settings (key, value) VALUES ('submission_close_day', '5') ON CONFLICT (key) DO NOTHING")

    # Create report_drafts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS report_drafts (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            report_type VARCHAR(50) NOT NULL,
            reporting_month VARCHAR(20) NOT NULL,
            form_data TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (username, report_type, reporting_month)
        )
    """)

    # Create indexes for better performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_worklog_username ON worklog(username)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_worklog_date ON worklog(date)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)
    """)

    # Migrate old 'IQAC Coordinator' role to 'School IQAC Coordinator'
    cursor.execute("UPDATE users SET role='School IQAC Coordinator' WHERE role='IQAC Coordinator'")

    # Default admin
    cursor.execute("SELECT * FROM users WHERE username='admin'")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO users (username, password, emp_id, email, gender, designation, department, role)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            'admin',
            generate_password_hash('admin123'),
            'CU0001',
            'admin@university.edu',
            'Male',
            'Director, IQAC',
            'IQAC',
            'Admin'
        ))
    conn.commit()
    conn.close()

# Initialize database on startup
try:
    print("Using PostgreSQL database")
    init_postgres()
except Exception as e:
    print(f"Warning: Could not initialize database: {e}")

# Ensure signed_reports upload directory exists
os.makedirs(os.path.join(os.path.dirname(__file__), 'static', 'signed_reports'), exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(__file__), 'static', 'attachments'), exist_ok=True)

ALLOWED_ATTACHMENT_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx'}

def _allowed_attachment(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_ATTACHMENT_EXTENSIONS

# ------------------ TEMPLATE FILTER ------------------

# ------------------ TEMPLATE FILTER ------------------
@app.template_filter("datetimeformat")
def datetimeformat(value):
    if not value:
        return value
    value_str = str(value).strip()
    try:
        return datetime.strptime(value_str, "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError:
        try:
            return datetime.strptime(value_str, "%Y-%m").strftime("%m-%Y")
        except ValueError:
            return value

@app.route("/")
def home():
    return redirect("/login")
    
# ------------------ LOGIN ------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        cur = get_cursor(conn)

        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()

        conn.close()

        if user and check_password_hash(user["password"], password):
            session["username"] = username
            session["role"] = user["role"]
            flash(f"Welcome, {username}!", "success")
            if user["role"].lower() == "admin":
                return redirect("/admin")
            elif user["role"].lower() in ("school iqac coordinator", "campus iqac coordinator"):
                return redirect("/iqac_dashboard")
            elif user["role"].lower() == "secretary":
                return redirect("/secretary_dashboard")
            else:
                return redirect("/dashboard")
        else:
            flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("Logged out successfully.", "success")
    return redirect("/login")


# ------------------ DASHBOARD (LANDING PAGE) ------------------
@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect("/login")

    username = session["username"]
    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Fetch user to check role
    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()

    if user["role"].lower() == "admin":
        conn.close()
        flash("Admins cannot access the employee dashboard.", "warning")
        return redirect("/admin")

    if user["role"].lower() in ("school iqac coordinator", "campus iqac coordinator"):
        conn.close()
        return redirect("/iqac_dashboard")

    # Fetch logs for stats
    cursor.execute("SELECT * FROM worklog WHERE username=%s", (username,))
    rows = cursor.fetchall()

    conn.close()

    # Calculate stats
    today = datetime.now().date()
    current_month = datetime.now().strftime("%Y-%m")
    
    # Week start (Monday)
    week_start = today - timedelta(days=today.weekday())
    
    total_entries = len(rows)
    month_entries = 0
    week_entries = 0
    recent_logs = []

    for r in rows:
        try:
            log_date = datetime.strptime(r["date"], "%Y-%m-%d").date()
        except:
            continue

        # Count month entries
        if r["date"].startswith(current_month):
            month_entries += 1
        
        # Count week entries
        if log_date >= week_start:
            week_entries += 1

        # Parse tasks - handle both JSON and legacy plain text format
        tasks_dict = {}
        task_raw = r["task"]
        if task_raw:
            try:
                tasks_dict = json.loads(task_raw)
            except (json.JSONDecodeError, TypeError):
                # Legacy format - use category as key
                if r["category"]:
                    tasks_dict = {r["category"]: task_raw}

        recent_logs.append({
            "date": r["date"],
            "category": r["category"],
            "task": r["task"],
            "tasks_dict": tasks_dict,
            "parsed_date": log_date
        })

    # Sort and get last 5 entries
    recent_logs = sorted(recent_logs, key=lambda x: x["parsed_date"], reverse=True)[:5]

    return render_template(
        "dashboard.html", 
        username=username, 
        total_entries=total_entries,
        month_entries=month_entries,
        week_entries=week_entries,
        recent_logs=recent_logs
    )


# ------------------ USER: ADD ENTRY ------------------
@app.route("/user_add_entry", methods=["GET", "POST"])
def user_add_entry():
    if "username" not in session:
        return redirect("/login")

    username = session["username"]
    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Fetch user to check role
    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()

    if user["role"].lower() == "admin":
        conn.close()
        flash("Admins cannot access this page.", "warning")
        return redirect("/admin")

    if user["role"].lower() in ("school iqac coordinator", "campus iqac coordinator"):
        conn.close()
        flash("IQAC Coordinators do not have access to worklog entries.", "warning")
        return redirect("/iqac_dashboard")

    # Handle form submit
    if request.method == "POST":
        date_input = request.form["date"]
        today = datetime.now().date()
        today_iso = today.strftime("%Y-%m-%d")
        current_day = today.day
        current_month = today.month
        current_year = today.year
        
        # Calculate min_date based on the 2nd of month rule
        if current_day <= 2:
            # Allow previous month dates until 2nd of current month
            if current_month == 1:
                # January - previous month is December of last year
                min_date = today.replace(year=current_year - 1, month=12, day=1)
            else:
                min_date = today.replace(month=current_month - 1, day=1)
        else:
            # After 2nd, only allow current month dates
            min_date = today.replace(day=1)
        
        min_date_iso = min_date.strftime("%Y-%m-%d")

        # Normalize date input
        try:
            parsed = datetime.strptime(date_input, "%Y-%m-%d")
        except:
            try:
                parsed = datetime.strptime(date_input, "%d/%m/%Y")
            except:
                parsed = datetime.now()
        date_iso = parsed.strftime("%Y-%m-%d")
        parsed_date = parsed.date()

        if date_iso > today_iso:
            flash("Date cannot be in the future.", "danger")
        elif parsed_date < min_date:
            if current_day <= 2:
                flash("You can only add entries for this month or the previous month.", "danger")
            else:
                flash("Previous month is locked after the 2nd. You can only add entries for the current month.", "danger")
        else:
            cursor.execute("SELECT id FROM worklog WHERE username=%s AND date=%s", (username, date_iso))
            exists = cursor.fetchone()

            if exists:
                flash("An entry already exists for this date.", "danger")
            else:
                # Check if it's a holiday or leave
                is_holiday = request.form.get("is_holiday") == "1"
                is_leave = request.form.get("is_leave") == "1"
                
                if is_holiday:
                    # Create holiday entry
                    category_str = "Holiday"
                    task_json = json.dumps({"Holiday": "Holiday"})
                    
                    cursor.execute("INSERT INTO worklog (username, date, category, task) VALUES (%s, %s, %s, %s)",
                                   (username, date_iso, category_str, task_json))
                    conn.commit()
                    conn.close()
                    flash("Holiday entry added successfully!", "success")
                    return redirect("/dashboard")
                    
                elif is_leave:
                    # Create leave entry
                    category_str = "Leave"
                    task_json = json.dumps({"Leave": "Leave"})
                    
                    cursor.execute("INSERT INTO worklog (username, date, category, task) VALUES (%s, %s, %s, %s)",
                                   (username, date_iso, category_str, task_json))
                    conn.commit()
                    conn.close()
                    flash("Leave entry added successfully!", "success")
                    return redirect("/dashboard")
                    
                else:
                    # Regular worklog entry
                    # Get selected categories
                    categories = request.form.getlist("categories")

                    # Build category-wise tasks dictionary
                    category_tasks = {}
                    task_mapping = {
                        "Documentation and Audits": "task_documentation",
                        "Rankings": "task_rankings",
                        "Publications": "task_publications",
                        "Training and Development": "task_training",
                        "Strategic Initiatives": "task_strategic",
                        "Others": "task_others"
                    }

                    for cat in categories:
                        field_name = task_mapping.get(cat)
                        if field_name:
                            task_text = request.form.get(field_name, "").strip()
                            if task_text:
                                category_tasks[cat] = task_text

                    if not category_tasks:
                        flash("Please select at least one category and enter tasks.", "danger")
                    else:
                        # Handle optional file attachment
                        attachment_path = None
                        uploaded_file = request.files.get("attachment")
                        if uploaded_file and uploaded_file.filename and _allowed_attachment(uploaded_file.filename):
                            ext = uploaded_file.filename.rsplit('.', 1)[1].lower()
                            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                            save_name = f"{secure_filename(username)}_{date_iso}_{timestamp}.{ext}"
                            save_dir = os.path.join(os.path.dirname(__file__), 'static', 'attachments')
                            uploaded_file.save(os.path.join(save_dir, save_name))
                            attachment_path = f"attachments/{save_name}"

                        # Store categories as comma-separated and tasks as JSON
                        category_str = ", ".join(category_tasks.keys())
                        task_json = json.dumps(category_tasks)

                        cursor.execute("""
                            INSERT INTO worklog (username, date, status, category, task, attachment)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (username, date_iso, "Present", category_str, task_json, attachment_path))
                        conn.commit()
                        conn.close()
                        flash("Worklog entry added successfully!", "success")
                        return redirect("/dashboard")

    conn.close()
    return render_template("user_add_entry.html", username=username)


# ------------------ USER: VIEW ENTRIES ------------------
@app.route("/user_view_entries")
def user_view_entries():
    if "username" not in session:
        return redirect("/login")

    username = session["username"]
    category_filter = request.args.get("category_filter", "All")
    
    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Fetch user to check role
    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()

    if user["role"].lower() == "admin":
        conn.close()
        flash("Admins cannot access this page.", "warning")
        return redirect("/admin")

    if user["role"].lower() in ("school iqac coordinator", "campus iqac coordinator"):
        conn.close()
        flash("IQAC Coordinators do not have access to worklog entries.", "warning")
        return redirect("/iqac_dashboard")

    # Fetch logs
    cursor.execute("SELECT * FROM worklog WHERE username=%s", (username,))
    rows = cursor.fetchall()

    conn.close()

    # Evaluate edit/delete eligibility
    today = datetime.now().date()
    logs_processed = []

    for r in rows:
        try:
            log_date = datetime.strptime(r["date"], "%Y-%m-%d").date()
        except:
            continue

        diff = (today - log_date).days
        
        # Parse tasks - handle both JSON and legacy plain text format
        tasks_dict = {}
        task_raw = r["task"]
        if task_raw:
            try:
                tasks_dict = json.loads(task_raw)
            except (json.JSONDecodeError, TypeError):
                # Legacy format - use category as key
                if r["category"]:
                    tasks_dict = {r["category"]: task_raw}
        
        # Apply category filter
        if category_filter and category_filter != "All":
            if category_filter in tasks_dict:
                # Only show the selected category's task
                tasks_dict = {category_filter: tasks_dict[category_filter]}
            else:
                # Skip this log if selected category not present
                continue
        
        logs_processed.append({
            "id": r["id"],
            "date": r["date"],
            "category": r["category"],
            "task": r["task"],
            "tasks_dict": tasks_dict,
            "can_edit": diff <= 7,
            "parsed_date": log_date
        })

    logs_sorted = sorted(logs_processed, key=lambda x: x["parsed_date"], reverse=True)

    return render_template("user_view_entries.html", username=username, logs=logs_sorted, category_filter=category_filter)


# ------------------ USER: GENERATE REPORT ------------------
@app.route("/user_report", methods=["GET", "POST"])
def user_report():
    if "username" not in session:
        return redirect("/login")

    username = session["username"]
    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Fetch user info
    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()

    if user["role"].lower() == "admin":
        conn.close()
        flash("Admins should use the Admin Report page.", "warning")
        return redirect("/admin")

    if user["role"].lower() in ("school iqac coordinator", "campus iqac coordinator"):
        conn.close()
        flash("IQAC Coordinators do not have worklog reports.", "warning")
        return redirect("/iqac_dashboard")

    logs = []
    filter_mode = "date"
    from_date = None
    to_date = None
    selected_month = None
    selected_academic_year = None
    category_filter = "All"

    if request.method == "POST":
        filter_mode = request.form.get("filter_mode")
        from_date = request.form.get("from_date")
        to_date = request.form.get("to_date")
        selected_month = request.form.get("month")
        selected_academic_year = request.form.get("academic_year")
        category_filter = request.form.get("category_filter", "All")

        if filter_mode == "academic_year":
            if not selected_academic_year:
                flash("Please select an academic year.", "danger")
            else:
                # Academic year format: "2025-2026" means May 2025 to April 2026
                start_year, end_year = selected_academic_year.split("-")
                first = f"{start_year}-05-01"  # May 1st of start year
                last = f"{end_year}-04-30"     # April 30th of end year

                cursor.execute("""
                    SELECT w.*, u.emp_id, u.designation, u.username
                    FROM worklog w
                    JOIN users u ON w.username=u.username
                    WHERE w.username=%s AND w.date BETWEEN %s AND %s
                    ORDER BY w.date
                """, (username, first, last))

                logs = cursor.fetchall()

        elif filter_mode == "month":
            if not selected_month:
                flash("Please select a month.", "danger")
            else:
                year, month = selected_month.split("-")
                first = f"{year}-{month}-01"
                last = f"{year}-{month}-{calendar.monthrange(int(year), int(month))[1]}"

                cursor.execute("""
                    SELECT w.*, u.emp_id, u.designation, u.username
                    FROM worklog w
                    JOIN users u ON w.username=u.username
                    WHERE w.username=%s AND w.date BETWEEN %s AND %s
                    ORDER BY w.date
                """, (username, first, last))

                logs = cursor.fetchall()

        elif filter_mode == "date":
            if not from_date or not to_date:
                flash("Select From and To dates.", "danger")
            else:
                cursor.execute("""
                    SELECT w.*, u.emp_id, u.designation, u.username
                    FROM worklog w
                    JOIN users u ON w.username=u.username
                    WHERE w.username=%s AND w.date BETWEEN %s AND %s
                    ORDER BY w.date
                """, (username, from_date, to_date))

                logs = cursor.fetchall()

    # Process logs to parse JSON tasks and filter by category
    processed_logs = []
    for log in logs:
        log_dict = dict(log)
        tasks_dict = {}
        task_raw = log["task"]
        if task_raw:
            try:
                tasks_dict = json.loads(task_raw)
            except (json.JSONDecodeError, TypeError):
                # Legacy format - use category as key
                if log["category"]:
                    tasks_dict = {log["category"]: task_raw}
        
        # Apply category filter
        if category_filter and category_filter != "All":
            if category_filter in tasks_dict:
                # Only show the selected category's task
                tasks_dict = {category_filter: tasks_dict[category_filter]}
            else:
                # Skip this log if selected category not present
                continue
        
        log_dict["tasks_dict"] = tasks_dict
        processed_logs.append(log_dict)

    conn.close()

    return render_template(
        "user_report.html",
        logs=processed_logs,
        username=username,
        user=user,
        from_date=from_date,
        to_date=to_date,
        selected_month=selected_month,
        selected_academic_year=selected_academic_year,
        filter_mode=filter_mode,
        category_filter=category_filter,
        datetime=datetime
    )


# ------------------ EDIT ENTRY ------------------
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    if "username" not in session:
        return redirect("/login")

    username = session["username"]
    conn = get_db_connection()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM worklog WHERE id=%s AND username=%s", (id, username))
    log = cursor.fetchone()

    if not log:
        conn.close()
        flash("Entry not found.", "danger")
        return redirect("/user_view_entries")

    log_date = datetime.strptime(log["date"], "%Y-%m-%d").date()
    if (datetime.now().date() - log_date).days > 7:
        conn.close()
        flash("You can only edit entries from the last 7 days.", "danger")
        return redirect("/user_view_entries")

    if request.method == "POST":
        # Get selected categories
        categories = request.form.getlist("categories")
        
        # Build category-wise tasks dictionary
        category_tasks = {}
        task_mapping = {
            "Documentation and Audits": "task_documentation",
            "Rankings": "task_rankings",
            "Publications": "task_publications",
            "Training and Development": "task_training",
            "Strategic Initiatives": "task_strategic",
            "Others": "task_others"
        }
        
        for cat in categories:
            field_name = task_mapping.get(cat)
            if field_name:
                task_text = request.form.get(field_name, "").strip()
                if task_text:
                    category_tasks[cat] = task_text
        
        if not category_tasks:
            flash("Please select at least one category and enter tasks.", "danger")
        else:
            # Store categories as comma-separated and tasks as JSON
            category_str = ", ".join(category_tasks.keys())
            task_json = json.dumps(category_tasks)

            cursor.execute("UPDATE worklog SET category=%s, task=%s WHERE id=%s", (category_str, task_json, id))
            conn.commit()

            conn.close()
            flash("Entry updated successfully!", "success")
            return redirect("/user_view_entries")

    # Parse existing tasks for display
    tasks_dict = {}
    task_raw = log["task"]
    if task_raw:
        try:
            tasks_dict = json.loads(task_raw)
        except (json.JSONDecodeError, TypeError):
            # Legacy format - use category as key
            if log["category"]:
                tasks_dict = {log["category"]: task_raw}

    conn.close()

    return render_template("edit.html", log=log, tasks_dict=tasks_dict)

# ------------------ DELETE ENTRY ------------------
@app.route("/delete_entry/<int:id>", methods=["POST"])
def delete_entry(id):
    if "username" not in session:
        return redirect("/login")

    username = session["username"]
    conn = get_db_connection()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM worklog WHERE id=%s AND username=%s", (id, username))
    log = cursor.fetchone()

    if not log:
        conn.close()
        flash("Entry not found.", "danger")
        return redirect("/user_view_entries")

    log_date = datetime.strptime(log["date"], "%Y-%m-%d").date()
    if (datetime.now().date() - log_date).days > 7:
        conn.close()
        flash("You can only delete entries from the last 7 days.", "danger")
        return redirect("/user_view_entries")

    cursor.execute("DELETE FROM worklog WHERE id=%s", (id,))
    conn.commit()

    conn.close()
    flash("Entry deleted successfully!", "success")
    return redirect("/user_view_entries")

# ------------------ ADMIN DASHBOARD ------------------
@app.route("/admin", methods=["GET", "POST"])
def admin_panel():
    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Ensure admin
    cursor.execute("SELECT * FROM users WHERE username=%s", (session["username"],))
    admin = cursor.fetchone()

    if not admin or admin["role"].lower() != "admin":
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/dashboard")

    # Fetch employees for dropdown (exclude Admin and Coordinators)
    cursor.execute("SELECT username, emp_id FROM users WHERE role NOT IN ('Admin', 'School IQAC Coordinator', 'Campus IQAC Coordinator') ORDER BY username")
    users = cursor.fetchall()

    # Get stats for dashboard cards
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role != 'Admin'")
    total_users = cursor.fetchone()['count']

    cursor.execute("SELECT COUNT(*) as count FROM worklog")
    total_entries = cursor.fetchone()['count']

    # This month's entries
    now = datetime.now()
    month_start = f"{now.year}-{now.month:02d}-01"
    month_end = f"{now.year}-{now.month:02d}-{calendar.monthrange(now.year, now.month)[1]}"
    cursor.execute("SELECT COUNT(*) as count FROM worklog WHERE date BETWEEN %s AND %s", (month_start, month_end))
    month_entries = cursor.fetchone()['count']

    # IQAC Coordinator report submission progress — reports are for the previous month
    prev = now.replace(day=1) - timedelta(days=1)
    current_report_month = prev.strftime("%Y-%m")
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role IN ('School IQAC Coordinator', 'Campus IQAC Coordinator')")
    total_coordinators = cursor.fetchone()['count']
    cursor.execute("""
        SELECT COUNT(DISTINCT sr.username) as count FROM signed_reports sr
        JOIN users u ON sr.username = u.username
        WHERE sr.reporting_month = %s
        AND sr.status IN ('uploaded', 'reviewed')
        AND u.role IN ('School IQAC Coordinator', 'Campus IQAC Coordinator')
    """, (current_report_month,))
    submitted_coordinators = cursor.fetchone()['count']
    submission_pct = int((submitted_coordinators / total_coordinators * 100) if total_coordinators > 0 else 0)

    # Coordinators with signed PDF uploaded
    cursor.execute("""
        SELECT DISTINCT u.username, u.full_name FROM users u
        JOIN signed_reports sr ON sr.username = u.username
        WHERE u.role IN ('School IQAC Coordinator', 'Campus IQAC Coordinator')
        AND sr.reporting_month = %s AND sr.status IN ('uploaded', 'reviewed')
    """, (current_report_month,))
    submitted_coordinator_names = [r['full_name'] or r['username'] for r in cursor.fetchall()]

    # Coordinators with draft saved but not yet uploaded
    cursor.execute("""
        SELECT DISTINCT u.username, u.full_name FROM users u
        JOIN signed_reports sr ON sr.username = u.username
        WHERE u.role IN ('School IQAC Coordinator', 'Campus IQAC Coordinator')
        AND sr.reporting_month = %s AND sr.status IN ('pending_upload', 'corrections_requested')
    """, (current_report_month,))
    draft_coordinator_names = [r['full_name'] or r['username'] for r in cursor.fetchall()]

    # Coordinators with nothing done
    cursor.execute("""
        SELECT username, full_name FROM users WHERE role IN ('School IQAC Coordinator', 'Campus IQAC Coordinator')
        AND username NOT IN (
            SELECT DISTINCT username FROM signed_reports WHERE reporting_month = %s
        )
    """, (current_report_month,))
    pending_coordinators = [r['full_name'] or r['username'] for r in cursor.fetchall()]

    # Handle submission window settings update
    if request.method == "POST" and "update_window" in request.form:
        new_close = request.form.get("submission_close_day", "5").strip()
        if new_close.isdigit():
            close_i = int(new_close)
            if 1 <= close_i <= 28:
                cursor.execute("UPDATE app_settings SET value='1' WHERE key='submission_open_day'")
                cursor.execute("UPDATE app_settings SET value=%s WHERE key='submission_close_day'", (new_close,))
                conn.commit()
                flash(f"Submission window updated: 1st to {close_i}th of each month.", "success")
            else:
                flash("Invalid close day. Must be between 1 and 28.", "danger")
        conn.close()
        return redirect("/admin")

    # Fetch coordinators for dropdown
    cursor.execute("SELECT username, role FROM users WHERE role IN ('School IQAC Coordinator', 'Campus IQAC Coordinator') ORDER BY username")
    coordinators = cursor.fetchall()

    # Coordinator summary form handling
    coord_reports = None
    coord_user = "All"
    coord_report_type = "monthly"
    coord_from_month = f"{now.year}-01"
    coord_to_month = f"{now.year}-{now.month:02d}"
    coord_year = str(now.year)

    if request.method == "POST" and "coord_form" in request.form:
        coord_user = request.form.get("coord_user", "All")
        coord_report_type = request.form.get("coord_report_type", "monthly")
        coord_from_month = request.form.get("coord_from_month", f"{now.year}-01")
        coord_to_month = request.form.get("coord_to_month", f"{now.year}-{now.month:02d}")
        coord_year = request.form.get("coord_year", str(now.year))

        year_int = int(coord_year)
        if coord_report_type == "yearly":
            start_m = f"{year_int}-01"
            end_m = f"{year_int}-12"
        else:
            start_m = coord_from_month or f"{year_int}-01"
            end_m = coord_to_month or f"{year_int}-{now.month:02d}"

        if coord_user == "All":
            cursor.execute("""
                SELECT sr.*, u.designation, u.department, u.role
                FROM signed_reports sr
                JOIN users u ON sr.username = u.username
                WHERE sr.reporting_month BETWEEN %s AND %s
                ORDER BY sr.reporting_month, sr.username
            """, (start_m, end_m))
        else:
            cursor.execute("""
                SELECT sr.*, u.designation, u.department, u.role
                FROM signed_reports sr
                JOIN users u ON sr.username = u.username
                WHERE sr.username = %s AND sr.reporting_month BETWEEN %s AND %s
                ORDER BY sr.reporting_month
            """, (coord_user, start_m, end_m))

        coord_reports = cursor.fetchall()

    # Initialize filter variables
    filter_mode = "month"
    selected_month = datetime.now().strftime("%Y-%m")
    from_date = None
    to_date = None
    selected_academic_year = None
    selected_user = "All"
    category_filter = "All"

    # Get filter values from form
    if request.method == "POST" and "coord_form" not in request.form:
        filter_mode = request.form.get("filter_mode", "month")
        selected_month = request.form.get("month", datetime.now().strftime("%Y-%m"))
        from_date = request.form.get("from_date")
        to_date = request.form.get("to_date")
        selected_academic_year = request.form.get("academic_year")
        selected_user = request.form.get("user", "All")
        category_filter = request.form.get("category_filter", "All")

    # Build date range based on filter mode
    if filter_mode == "academic_year" and selected_academic_year:
        start_year, end_year = selected_academic_year.split("-")
        first_date = f"{start_year}-05-01"
        last_date = f"{end_year}-04-30"
    elif filter_mode == "date" and from_date and to_date:
        first_date = from_date
        last_date = to_date
    else:
        # Default to month-wise
        year, month = selected_month.split("-")
        first_date = f"{year}-{month}-01"
        last_date = f"{year}-{month}-{calendar.monthrange(int(year), int(month))[1]}"

    # Build query based on filters
    if selected_user == "All":
        if category_filter == "All":
            cursor.execute("""
                SELECT username, COUNT(*) AS count
                FROM worklog
                WHERE date BETWEEN %s AND %s
                GROUP BY username
                ORDER BY count DESC
            """, (first_date, last_date))
        else:
            cursor.execute("""
                SELECT username, COUNT(*) AS count
                FROM worklog
                WHERE date BETWEEN %s AND %s
                  AND task::text LIKE %s
                GROUP BY username
                ORDER BY count DESC
            """, (first_date, last_date, f'%"{category_filter}"%'))
    else:
        if category_filter == "All":
            cursor.execute("""
                SELECT username, COUNT(*) AS count
                FROM worklog
                WHERE date BETWEEN %s AND %s AND username = %s
                GROUP BY username
            """, (first_date, last_date, selected_user))
        else:
            cursor.execute("""
                SELECT username, COUNT(*) AS count
                FROM worklog
                WHERE date BETWEEN %s AND %s AND username = %s
                  AND task::text LIKE %s
                GROUP BY username
            """, (first_date, last_date, selected_user, f'%"{category_filter}"%'))

    summary = cursor.fetchall()
    conn.close()

    # Format month for display (e.g., "January 2026")
    try:
        display_month = datetime.strptime(selected_month, "%Y-%m").strftime("%m-%Y")
    except:
        display_month = datetime.now().strftime("%m-%Y")

    return render_template(
        "admin.html",
        username=session["username"],
        current_month=display_month,
        selected_month=selected_month,
        filter_mode=filter_mode,
        from_date=from_date,
        to_date=to_date,
        selected_academic_year=selected_academic_year,
        selected_user=selected_user,
        category_filter=category_filter,
        users=users,
        summary=summary,
        total_users=total_users,
        total_entries=total_entries,
        month_entries=month_entries,
        total_coordinators=total_coordinators,
        submitted_coordinators=submitted_coordinators,
        submission_pct=submission_pct,
        pending_coordinators=pending_coordinators,
        submitted_coordinator_names=submitted_coordinator_names,
        draft_coordinator_names=draft_coordinator_names,
        current_report_month=datetime.strptime(current_report_month, "%Y-%m").strftime("%m-%Y"),
        **dict(zip(('submission_open_day', 'submission_close_day'), get_submission_window())),
        coordinators=coordinators,
        coord_reports=coord_reports,
        coord_user=coord_user,
        coord_report_type=coord_report_type,
        coord_from_month=coord_from_month,
        coord_to_month=coord_to_month,
        coord_year=coord_year,
    )


# ------------------ ADMIN: ADD USER ------------------
@app.route("/admin_add_user", methods=["GET", "POST"])
def admin_add_user():
    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Check admin
    cursor.execute("SELECT * FROM users WHERE username=%s", (session["username"],))
    admin = cursor.fetchone()

    if not admin or admin["role"].lower() != "admin":
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/dashboard")

    if request.method == "POST":
        username = request.form["username"]
        full_name = request.form.get("full_name", "").strip()
        emp_id = request.form["emp_id"]
        email = request.form["email"]
        gender = request.form["gender"]
        designation = request.form["designation"]
        department = request.form["department"]
        role = request.form["role"]

        password = "".join(random.choices(string.ascii_letters + string.digits, k=8))
        hashed = generate_password_hash(password)

        # Check if exists
        cursor.execute("SELECT * FROM users WHERE username=%s OR email=%s", (username, email))
        exists = cursor.fetchone()

        if exists:
            flash("Username or email already exists.", "danger")
        else:
            cursor.execute("""
                INSERT INTO users (username, password, emp_id, email, gender, designation, department, role, full_name)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (username, hashed, emp_id, email, gender, designation, department, role, full_name or None))
            conn.commit()

            # Send credentials email
            try:
                body = f"""Dear {username},

Your IQAC Worklog account has been created.

Username: {username}
Password: {password}

Login: https://iqacworklog.christuniversity.in/login

Regards,
IQAC Admin"""
                send_email(email, "IQAC Worklog Account Created", body)
                flash("User added and credentials emailed.", "success")

            except Exception as e:
                flash(f"User added but email failed: {e}", "warning")

            return redirect("/admin")

    conn.close()
    return render_template("admin_add_user.html")


# ------------------ FORGOT PASSWORD ------------------
@app.route("/forgot_password", methods=["POST"])
def forgot_password():
    username = request.form["username"]
    email = request.form["email"]

    conn = get_db_connection()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM users WHERE username=%s AND email=%s", (username, email))
    user = cursor.fetchone()

    if not user:
        conn.close()
        flash("Invalid username or email.", "danger")
        return redirect("/login")

    new_password = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    hashed = generate_password_hash(new_password)

    cursor.execute("UPDATE users SET password=%s WHERE username=%s", (hashed, username))
    conn.commit()
    conn.close()

    # Email password
    try:
        body = f"""Dear {username},

Your password for the IQAC Worklog account has been successfully reset. Please find your updated login credentials below:

Username: {username}
New Password: {new_password}

You may log in using the following link:
https://iqacworklog.christuniversity.in

If you did not request this reset or require any assistance, please contact the admin.

Regards,
IQAC Admin"""
        send_email(email, "IQAC Worklog Password Reset", body)
        flash("New password emailed to you.", "success")

    except Exception as e:
        flash(f"Password reset but email failed: {e}", "danger")

    return redirect("/login")


# ------------------ ADMIN REPORT (DATE + MONTH + ACADEMIC YEAR FILTERS) ------------------
@app.route("/admin_report", methods=["GET", "POST"])
def admin_report():
    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Ensure admin or secretary
    cursor.execute("SELECT * FROM users WHERE username=%s", (session["username"],))
    admin = cursor.fetchone()

    if not admin or admin["role"].lower() not in ("admin", "secretary"):
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/dashboard")

    # Fetch users
    cursor.execute("SELECT username, emp_id FROM users WHERE role NOT IN ('Admin', 'School IQAC Coordinator', 'Campus IQAC Coordinator') ORDER BY username")
    users = cursor.fetchall()

    logs = []
    selected_user = None
    filter_mode = "date"
    from_date = None
    to_date = None
    selected_month = None
    selected_academic_year = None
    category_filter = "All"

    if request.method == "POST":
        selected_user = request.form.get("user")
        filter_mode = request.form.get("filter_mode")
        from_date = request.form.get("from_date")
        to_date = request.form.get("to_date")
        selected_month = request.form.get("month")
        selected_academic_year = request.form.get("academic_year")
        category_filter = request.form.get("category_filter", "All")

        if not selected_user:
            flash("Please select a user.", "danger")

        elif filter_mode == "academic_year":
            if not selected_academic_year:
                flash("Please select an academic year.", "danger")
            else:
                # Academic year format: "2025-2026" means May 2025 to April 2026
                start_year, end_year = selected_academic_year.split("-")
                first = f"{start_year}-05-01"  # May 1st of start year
                last = f"{end_year}-04-30"     # April 30th of end year

                if selected_user == "All":
                    cursor.execute("""
                        SELECT w.*, u.emp_id, u.designation, u.username
                        FROM worklog w
                        JOIN users u ON w.username=u.username
                        WHERE w.date BETWEEN %s AND %s
                        ORDER BY w.username, w.date
                    """, (first, last))
                else:
                    cursor.execute("""
                        SELECT w.*, u.emp_id, u.designation, u.username
                        FROM worklog w
                        JOIN users u ON w.username=u.username
                        WHERE w.username=%s AND w.date BETWEEN %s AND %s
                        ORDER BY w.date
                    """, (selected_user, first, last))

                logs = cursor.fetchall()

        elif filter_mode == "month":
            if not selected_month:
                flash("Please select a month.", "danger")
            else:
                year, month = selected_month.split("-")
                first = f"{year}-{month}-01"
                last = f"{year}-{month}-{calendar.monthrange(int(year), int(month))[1]}"

                if selected_user == "All":
                    cursor.execute("""
                        SELECT w.*, u.emp_id, u.designation, u.username
                        FROM worklog w
                        JOIN users u ON w.username=u.username
                        WHERE w.date BETWEEN %s AND %s
                        ORDER BY w.username, w.date
                    """, (first, last))
                else:
                    cursor.execute("""
                        SELECT w.*, u.emp_id, u.designation, u.username
                        FROM worklog w
                        JOIN users u ON w.username=u.username
                        WHERE w.username=%s AND w.date BETWEEN %s AND %s
                        ORDER BY w.date
                    """, (selected_user, first, last))

                logs = cursor.fetchall()

        elif filter_mode == "date":
            if not from_date or not to_date:
                flash("Select From and To dates.", "danger")
            else:
                if selected_user == "All":
                    cursor.execute("""
                        SELECT w.*, u.emp_id, u.designation, u.username
                        FROM worklog w
                        JOIN users u ON w.username=u.username
                        WHERE w.date BETWEEN %s AND %s
                        ORDER BY w.username, w.date
                    """, (from_date, to_date))
                else:
                    cursor.execute("""
                        SELECT w.*, u.emp_id, u.designation, u.username
                        FROM worklog w
                        JOIN users u ON w.username=u.username
                        WHERE w.username=%s AND w.date BETWEEN %s AND %s
                        ORDER BY w.date
                    """, (selected_user, from_date, to_date))

                logs = cursor.fetchall()

    # Process logs to parse JSON tasks and filter by category
    processed_logs = []
    for log in logs:
        log_dict = dict(log)
        tasks_dict = {}
        task_raw = log["task"]
        if task_raw:
            try:
                tasks_dict = json.loads(task_raw)
            except (json.JSONDecodeError, TypeError):
                # Legacy format - use category as key
                if log["category"]:
                    tasks_dict = {log["category"]: task_raw}

        # Apply category filter
        if category_filter and category_filter != "All":
            if category_filter in tasks_dict:
                # Only show the selected category's task
                tasks_dict = {category_filter: tasks_dict[category_filter]}
            else:
                # Skip this log if selected category not present
                continue

        log_dict["tasks_dict"] = tasks_dict
        processed_logs.append(log_dict)

    conn.close()

    return render_template(
        "admin_report.html",
        users=users,
        logs=processed_logs,
        selected_user=selected_user,
        from_date=from_date,
        to_date=to_date,
        selected_month=selected_month,
        selected_academic_year=selected_academic_year,
        filter_mode=filter_mode,
        category_filter=category_filter,
        user=admin,
        datetime=datetime
    )


@app.route("/admin_report_ai", methods=["GET", "POST"])
def admin_report_ai():
    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Ensure admin
    cursor.execute("SELECT * FROM users WHERE username=%s", (session["username"],))
    admin = cursor.fetchone()

    if not admin or admin["role"].lower() != "admin":
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/dashboard")

    # Fetch users
    cursor.execute("SELECT username, emp_id FROM users WHERE role NOT IN ('Admin', 'School IQAC Coordinator', 'Campus IQAC Coordinator') ORDER BY username")
    users = cursor.fetchall()

    logs = []
    selected_user = None
    filter_mode = "date"
    from_date = None
    to_date = None
    selected_month = None
    selected_academic_year = None
    category_filter = "All"
    ai_summary = None
    ai_error = None

    if request.method == "POST":
        selected_user = request.form.get("user")
        filter_mode = request.form.get("filter_mode")
        from_date = request.form.get("from_date")
        to_date = request.form.get("to_date")
        selected_month = request.form.get("month")
        selected_academic_year = request.form.get("academic_year")
        category_filter = request.form.get("category_filter", "All")

        if not selected_user:
            flash("Please select a user.", "danger")

        elif filter_mode == "academic_year":
            if not selected_academic_year:
                flash("Please select an academic year.", "danger")
            else:
                # Academic year format: "2025-2026" means May 2025 to April 2026
                start_year, end_year = selected_academic_year.split("-")
                first = f"{start_year}-05-01"  # May 1st of start year
                last = f"{end_year}-04-30"     # April 30th of end year

                if selected_user == "All":
                    cursor.execute("""
                        SELECT w.*, u.emp_id, u.designation, u.username
                        FROM worklog w
                        JOIN users u ON w.username=u.username
                        WHERE w.date BETWEEN %s AND %s
                        ORDER BY w.username, w.date
                    """, (first, last))
                else:
                    cursor.execute("""
                        SELECT w.*, u.emp_id, u.designation, u.username
                        FROM worklog w
                        JOIN users u ON w.username=u.username
                        WHERE w.username=%s AND w.date BETWEEN %s AND %s
                        ORDER BY w.date
                    """, (selected_user, first, last))

                logs = cursor.fetchall()

        elif filter_mode == "month":
            if not selected_month:
                flash("Please select a month.", "danger")
            else:
                year, month = selected_month.split("-")
                first = f"{year}-{month}-01"
                last = f"{year}-{month}-{calendar.monthrange(int(year), int(month))[1]}"

                if selected_user == "All":
                    cursor.execute("""
                        SELECT w.*, u.emp_id, u.designation, u.username
                        FROM worklog w
                        JOIN users u ON w.username=u.username
                        WHERE w.date BETWEEN %s AND %s
                        ORDER BY w.username, w.date
                    """, (first, last))
                else:
                    cursor.execute("""
                        SELECT w.*, u.emp_id, u.designation, u.username
                        FROM worklog w
                        JOIN users u ON w.username=u.username
                        WHERE w.username=%s AND w.date BETWEEN %s AND %s
                        ORDER BY w.date
                    """, (selected_user, first, last))

                logs = cursor.fetchall()

        elif filter_mode == "date":
            if not from_date or not to_date:
                flash("Select From and To dates.", "danger")
            else:
                if selected_user == "All":
                    cursor.execute("""
                        SELECT w.*, u.emp_id, u.designation, u.username
                        FROM worklog w
                        JOIN users u ON w.username=u.username
                        WHERE w.date BETWEEN %s AND %s
                        ORDER BY w.username, w.date
                    """, (from_date, to_date))
                else:
                    cursor.execute("""
                        SELECT w.*, u.emp_id, u.designation, u.username
                        FROM worklog w
                        JOIN users u ON w.username=u.username
                        WHERE w.username=%s AND w.date BETWEEN %s AND %s
                        ORDER BY w.date
                    """, (selected_user, from_date, to_date))

                logs = cursor.fetchall()

    # Process logs to parse JSON tasks and filter by category
    processed_logs = []
    for log in logs:
        log_dict = dict(log)
        tasks_dict = {}
        task_raw = log["task"]
        if task_raw:
            try:
                tasks_dict = json.loads(task_raw)
            except (json.JSONDecodeError, TypeError):
                # Legacy format - use category as key
                if log["category"]:
                    tasks_dict = {log["category"]: task_raw}

        # Apply category filter
        if category_filter and category_filter != "All":
            if category_filter in tasks_dict:
                # Only show the selected category's task
                tasks_dict = {category_filter: tasks_dict[category_filter]}
            else:
                # Skip this log if selected category not present
                continue

        log_dict["tasks_dict"] = tasks_dict
        processed_logs.append(log_dict)

    if request.method == "POST" and processed_logs:
        if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
            ai_error = "Gemini API key is not configured. Please add GEMINI_API_KEY in your .env file."
        else:
            try:
                global ai_client
                if not ai_client:
                    ai_client = genai.Client(api_key=GEMINI_API_KEY)

                model_name = "gemini-2.0-flash"
                system_instruction = (
                    "You are an assistant summarizing worklog entries for an IQAC report. "
                    "Write in a formal, official report tone. Do not use markdown, bullets, or asterisks. "
                    "Do not include introductory or concluding remarks."
                )
                prompt = build_ai_summary_prompt(
                    processed_logs,
                    selected_user,
                    filter_mode,
                    from_date,
                    to_date,
                    selected_month,
                    selected_academic_year,
                    category_filter
                )
                response = ai_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction
                    )
                )
                ai_summary = (response.text or "").strip() if response else ""
                ai_summary = ai_summary.replace("**", "").replace("*", "")
                if not ai_summary:
                    ai_error = "AI summary could not be generated. Please try again."
            except Exception as e:
                ai_error = f"AI summary error: {str(e)}"

    conn.close()

    return render_template(
        "admin_report_ai.html",
        users=users,
        logs=processed_logs,
        selected_user=selected_user,
        from_date=from_date,
        to_date=to_date,
        selected_month=selected_month,
        selected_academic_year=selected_academic_year,
        filter_mode=filter_mode,
        category_filter=category_filter,
        user=admin,
        datetime=datetime,
        ai_summary=ai_summary,
        ai_error=ai_error
    )


# ------------------ ADMIN: MANAGE USERS ------------------
@app.route("/admin_manage_users")
def admin_manage_users():
    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Check admin
    cursor.execute("SELECT * FROM users WHERE username=%s", (session["username"],))
    admin = cursor.fetchone()

    if not admin or admin["role"].lower() != "admin":
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/dashboard")

    # Fetch all users
    cursor.execute("SELECT * FROM users ORDER BY role DESC, username ASC")
    users = cursor.fetchall()
    conn.close()

    return render_template("admin_manage_users.html", users=users)


# ------------------ ADMIN: EDIT USER ------------------
@app.route("/admin_edit_user/<int:id>", methods=["GET", "POST"])
def admin_edit_user(id):
    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Check admin
    cursor.execute("SELECT * FROM users WHERE username=%s", (session["username"],))
    admin = cursor.fetchone()

    if not admin or admin["role"].lower() != "admin":
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/dashboard")

    # Fetch user to edit
    cursor.execute("SELECT * FROM users WHERE id=%s", (id,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        flash("User not found.", "danger")
        return redirect("/admin_manage_users")

    if request.method == "POST":
        new_username = request.form["username"]
        full_name = request.form.get("full_name", "").strip()
        emp_id = request.form["emp_id"]
        email = request.form["email"]
        gender = request.form["gender"]
        designation = request.form["designation"]
        department = request.form["department"]
        role = request.form["role"]

        old_username = user["username"]

        # Check if new username/email conflicts with another user
        cursor.execute("SELECT * FROM users WHERE (username=%s OR email=%s) AND id!=%s", (new_username, email, id))
        conflict = cursor.fetchone()

        if conflict:
            flash("Username or email already exists for another user.", "danger")
        else:
            # Update user
            cursor.execute("""
                UPDATE users SET username=%s, emp_id=%s, email=%s, gender=%s,
                designation=%s, department=%s, role=%s, full_name=%s WHERE id=%s
            """, (new_username, emp_id, email, gender, designation, department, role, full_name or None, id))

            # Update worklog entries if username changed
            if old_username != new_username:
                cursor.execute("UPDATE worklog SET username=%s WHERE username=%s", (new_username, old_username))

            conn.commit()
            flash("User updated successfully!", "success")
            conn.close()
            return redirect("/admin_manage_users")

    conn.close()
    return render_template("admin_edit_user.html", user=user)


# ------------------ ADMIN: DELETE USER ------------------
@app.route("/admin_delete_user/<int:id>", methods=["POST"])
def admin_delete_user(id):
    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Check admin
    cursor.execute("SELECT * FROM users WHERE username=%s", (session["username"],))
    admin = cursor.fetchone()

    if not admin or admin["role"].lower() != "admin":
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/dashboard")

    # Fetch user to delete
    cursor.execute("SELECT * FROM users WHERE id=%s", (id,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        flash("User not found.", "danger")
        return redirect("/admin_manage_users")

    if user["username"] == "admin":
        conn.close()
        flash("Cannot delete the main admin account.", "danger")
        return redirect("/admin_manage_users")

    # Delete user's worklog entries first
    cursor.execute("DELETE FROM worklog WHERE username=%s", (user["username"],))

    # Delete user
    cursor.execute("DELETE FROM users WHERE id=%s", (id,))

    conn.commit()
    conn.close()

    flash(f"User '{user['username']}' and their worklog entries deleted successfully!", "success")
    return redirect("/admin_manage_users")


# ------------------ ADMIN: RESET USER PASSWORD ------------------
@app.route("/admin_reset_password/<int:id>", methods=["POST"])
def admin_reset_password(id):
    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Check admin
    cursor.execute("SELECT * FROM users WHERE username=%s", (session["username"],))
    admin = cursor.fetchone()

    if not admin or admin["role"].lower() != "admin":
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/dashboard")

    # Fetch user
    cursor.execute("SELECT * FROM users WHERE id=%s", (id,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        flash("User not found.", "danger")
        return redirect("/admin_manage_users")

    # Generate new password
    new_password = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    hashed = generate_password_hash(new_password)

    cursor.execute("UPDATE users SET password=%s WHERE id=%s", (hashed, id))
    conn.commit()
    conn.close()

    # Send email
    try:
        body = f"""Dear {user['username']},

Your password for the IQAC Worklog account has been successfully reset. Please find your updated login credentials below:

Username: {user['username']}
New Password: {new_password}

You may log in using the following link:
https://iqacworklog.christuniversity.in

If you did not request this reset or require any assistance, please contact the admin.

Regards,
IQAC Admin"""
        send_email(user["email"], "IQAC Worklog - Password Reset", body)
        flash(f"Password reset for '{user['username']}' and emailed successfully!", "success")

    except Exception as e:
        flash(f"Password reset but email failed: {e}", "warning")

    return redirect("/admin_manage_users")


# ------------------ EMAIL REMINDER ROUTES (for scheduler/cron) ------------------
@app.route("/send_29th_reminders")
def trigger_29th_reminders():
    """Trigger 29th reminder emails - can be called by scheduler"""
    today = datetime.now().date()
    
    # Only send on 29th of the month
    if today.day != 29:
        return f"Not the 29th. Today is {today.strftime('%d-%m-%Y')}", 400
    
    result = send_29th_reminder()
    return result, 200

@app.route("/send_1st_deadline_reminders")
def trigger_1st_deadline_reminders():
    """Trigger 1st deadline reminder emails - can be called by scheduler"""
    today = datetime.now().date()
    
    # Only send on 1st of the month
    if today.day != 1:
        return f"Not the 1st. Today is {today.strftime('%d-%m-%Y')}", 400
    
    result = send_1st_deadline_reminder()
    return result, 200

# ------------------ IQAC COORDINATOR REPORT REMINDERS ------------------
def send_iqac_report_reminder(is_deadline=False):
    """Send reminder to IQAC Coordinators who haven't submitted their monthly report."""
    today = datetime.now().date()
    # Report is for the current month
    reporting_month = today.strftime("%Y-%m")
    month_display = today.strftime("%m-%Y")
    deadline_str = today.replace(day=5).strftime("%d-%m-%Y")

    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Get all IQAC Coordinators
    cursor.execute("SELECT username, email FROM users WHERE role IN ('School IQAC Coordinator', 'Campus IQAC Coordinator')")
    coordinators = cursor.fetchall()

    sent_count = 0
    for coord in coordinators:
        username = coord['username']
        email = coord['email']

        # Check if they've already submitted for this month
        cursor.execute("""
            SELECT id FROM signed_reports
            WHERE username = %s AND reporting_month = %s
        """, (username, reporting_month))
        already_submitted = cursor.fetchone()

        if already_submitted:
            continue  # Already submitted, skip

        if is_deadline:
            subject = f"URGENT: IQAC Monthly Report Due TODAY — {month_display}"
            body = f"""Dear {username.title()},

This is a final reminder that your Monthly Work Done Report for {month_display} is due TODAY ({deadline_str}).

Please log in to the IQAC portal, generate your report, and upload the signed copy before end of day.

Portal: https://iqacworklog.christuniversity.in/login

If you have already submitted, please disregard this message.

---
This is an automated reminder. Please do not reply.
"""
        else:
            body = f"""Dear {username.title()},

This is a reminder that your Monthly Work Done Report for {month_display} is due by {deadline_str}.

Please log in to the IQAC portal, fill in your monthly report, download the PDF, sign it, and upload the signed copy before the deadline.

Portal: https://iqacworklog.christuniversity.in/login

If you have already submitted, please disregard this message.

---
This is an automated reminder. Please do not reply.
"""
            subject = f"IQAC Monthly Report Reminder — Submit by {deadline_str}"

        send_reminder_email(email, subject, body)
        sent_count += 1

    conn.close()
    return f"IQAC reminder sent to {sent_count} coordinator(s) who haven't submitted for {month_display}."


def send_auto_iqac_reminders():
    """Daily auto-reminder: fires on days 3–close_day of each month for pending coordinators."""
    today = datetime.now().date()
    open_day, close_day = get_submission_window()

    if not (open_day <= today.day <= close_day):
        return f"Not a reminder day (today is {today.day}). Reminders fire on days {open_day}–{close_day}."

    # Reporting month is always the previous month
    if today.month == 1:
        report_year, report_month = today.year - 1, 12
    else:
        report_year, report_month = today.year, today.month - 1
    reporting_month = f"{report_year}-{report_month:02d}"
    month_display = datetime(report_year, report_month, 1).strftime("%m-%Y")

    days_left = close_day - today.day
    deadline_date = today.replace(day=close_day).strftime("%d-%m-%Y")

    if days_left == 0:
        days_left_str = "TODAY is the last day"
        subject = f"URGENT: IQAC Report Due TODAY — {month_display}"
    elif days_left == 1:
        days_left_str = "only 1 day left"
        subject = f"IQAC Report Reminder — 1 Day Left — {month_display}"
    else:
        days_left_str = f"{days_left} days left"
        subject = f"IQAC Report Reminder — {days_left} Days Left — {month_display}"

    conn = get_db_connection()
    cursor = get_cursor(conn)
    cursor.execute(
        "SELECT username, email FROM users WHERE role IN ('School IQAC Coordinator', 'Campus IQAC Coordinator')"
    )
    coordinators = cursor.fetchall()

    sent_count = 0
    for coord in coordinators:
        cursor.execute(
            "SELECT id FROM signed_reports WHERE username=%s AND reporting_month=%s",
            (coord['username'], reporting_month)
        )
        if cursor.fetchone():
            continue

        body = f"""Dear {coord['username'].title()},

This is an automated reminder that your Monthly Work Done Report for {month_display} has not yet been submitted.

Deadline: {deadline_date} ({days_left_str})

Steps to complete:
  1. Log in to the IQAC portal
  2. Go to "Generate Monthly Report", fill in your work details, and download the PDF
  3. Sign and scan the printed copy
  4. Upload the signed copy under "Upload Signed Report"

Portal: https://iqacworklog.christuniversity.in/login

If you have already submitted, please disregard this message.

---
This is an automated reminder. Please do not reply to this email.
"""
        send_reminder_email(coord['email'], subject, body)
        sent_count += 1

    conn.close()
    return f"Auto IQAC reminder sent to {sent_count} coordinator(s) for {month_display} (day {today.day}, {days_left_str})."


@app.route("/auto_iqac_reminders")
def trigger_auto_iqac_reminders():
    """Called daily by external cron (e.g. Render cron job). Self-checks whether to send."""
    result = send_auto_iqac_reminders()
    return result, 200


@app.route("/admin_trigger_iqac_reminder", methods=["POST"])
def admin_trigger_iqac_reminder():
    """Admin manually triggers IQAC reminder emails."""
    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = get_cursor(conn)
    cursor.execute("SELECT * FROM users WHERE username=%s", (session["username"],))
    admin = cursor.fetchone()
    conn.close()

    if not admin or admin["role"].lower() != "admin":
        flash("Access denied.", "danger")
        return redirect("/dashboard")

    result = send_iqac_report_reminder(is_deadline=False)
    flash(result, "success")
    return redirect("/admin_signed_reports")


# ------------------ IQAC COORDINATOR DASHBOARD ------------------
@app.route("/iqac_dashboard")
def iqac_dashboard():
    if "username" not in session:
        return redirect("/login")

    username = session["username"]
    conn = get_db_connection()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()

    if not user or user["role"].lower() not in ("school iqac coordinator", "campus iqac coordinator"):
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/login")

    # Fetch this coordinator's submitted reports
    cursor.execute("SELECT * FROM signed_reports WHERE username=%s ORDER BY uploaded_at DESC", (username,))
    submitted_reports = cursor.fetchall()

    # Query workshop attachments from DB (Cloudinary URLs)
    months = [r['reporting_month'] for r in submitted_reports]
    workshop_attachments = {}
    if months:
        ws_conn = get_db_connection()
        ws_cur = get_cursor(ws_conn)
        ws_cur.execute("""
            SELECT reporting_month, filename, cloudinary_url, workshop_index
            FROM workshop_attachment_files
            WHERE username = %s AND reporting_month = ANY(%s)
            ORDER BY reporting_month, workshop_index
        """, (username, months))
        for row in ws_cur.fetchall():
            m = row["reporting_month"]
            if m not in workshop_attachments:
                workshop_attachments[m] = []
            workshop_attachments[m].append({'name': row["filename"], 'url': row["cloudinary_url"]})
        ws_conn.close()

    is_open, reporting_month_str, open_day, close_day, window_msg = check_submission_window()

    # Check if a draft exists for the active window's reporting month
    has_draft = False
    if is_open:
        cursor.execute("""
            SELECT 1 FROM report_drafts 
            WHERE username=%s AND reporting_month=%s
        """, (username, reporting_month_str))
        has_draft = cursor.fetchone() is not None

    conn.close()

    reporting_month_display = ""
    if reporting_month_str:
        try:
            ry, rm = map(int, reporting_month_str.split('-'))
            reporting_month_display = datetime(ry, rm, 1).strftime("%m-%Y")
        except Exception:
            reporting_month_display = reporting_month_str

    return render_template("iqac_coordinator_dashboard.html",
        username=username,
        submitted_reports=submitted_reports,
        upload_open=is_open,
        reporting_month_str=reporting_month_str,
        reporting_month_display=reporting_month_display,
        has_draft=has_draft,
        window_msg=window_msg,
        open_day=open_day,
        close_day=close_day,
        workshop_attachments=workshop_attachments,
    )


# ------------------ IQAC MONTHLY REPORT FORM ------------------
@app.route("/iqac_monthly_report")
def iqac_monthly_report():
    if "username" not in session:
        return redirect("/login")

    username = session["username"]
    conn = get_db_connection()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()

    if not user or user["role"].lower() not in ("school iqac coordinator", "campus iqac coordinator"):
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/login")

    _, reporting_month_str, _, _, _ = check_submission_window()
    reporting_month_display = datetime.strptime(reporting_month_str, "%Y-%m").strftime("%m-%Y")

    report_type = "aqar_coordinator" if is_aqar_coordinator(user) else "standard"

    # Fetch draft if exists
    cursor.execute("""
        SELECT form_data FROM report_drafts 
        WHERE username=%s AND report_type=%s AND reporting_month=%s
    """, (username, report_type, reporting_month_str))
    draft_row = cursor.fetchone()

    # Check if report is locked
    cursor.execute("""
        SELECT status, remarks FROM signed_reports 
        WHERE username=%s AND reporting_month=%s
    """, (username, reporting_month_str))
    signed_row = cursor.fetchone()
    locked = signed_row is not None and signed_row["status"] in ('pending_upload', 'uploaded', 'reviewed')
    can_unlock = signed_row is not None and signed_row["status"] == 'pending_upload'
    rejection_remarks = signed_row["remarks"] if (signed_row and signed_row["status"] == 'corrections_requested') else None

    # Scan for existing workshop files
    ws_files_map = {}
    ws_upload_dir = os.path.join(app.root_path, 'static', 'signed_reports', 'workshop_attachments', username, reporting_month_str)
    if os.path.exists(ws_upload_dir):
        for f in os.listdir(ws_upload_dir):
            if f.startswith("workshop_"):
                try:
                    parts = os.path.splitext(f)[0].split("_")
                    if len(parts) > 1:
                        idx = int(parts[1]) - 1
                        ws_files_map[idx] = f
                except Exception:
                    pass

    conn.close()

    import json
    draft_data = None
    if draft_row:
        try:
            draft_data = json.loads(draft_row["form_data"])
        except Exception:
            pass

    # AQAR coordinators see the AQAR-aligned report
    if is_aqar_coordinator(user):
        return render_template("iqac_coordinator_report.html", username=username, user=user,
                               reporting_month_str=reporting_month_str,
                               reporting_month_display=reporting_month_display,
                               aqar_coordinator_names=AQAR_COORDINATOR_NAMES,
                               draft_data=draft_data,
                               locked=locked,
                               can_unlock=can_unlock,
                               rejection_remarks=rejection_remarks,
                               ws_files_map=ws_files_map)

    return render_template("iqac_monthly_report.html", username=username, user=user,
                           reporting_month_str=reporting_month_str,
                           reporting_month_display=reporting_month_display,
                           draft_data=draft_data,
                           locked=locked,
                           can_unlock=can_unlock,
                           rejection_remarks=rejection_remarks,
                           ws_files_map=ws_files_map)


@app.route("/iqac_report/save_draft", methods=["POST"])
def iqac_report_save_draft():
    if "username" not in session:
        return {"success": False, "error": "Not logged in"}, 401

    username = session["username"]
    conn = get_db_connection()
    cursor = get_cursor(conn)
    try:
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cursor.fetchone()
        if not user or user["role"].lower() not in ("school iqac coordinator", "campus iqac coordinator"):
            return {"success": False, "error": "Access denied"}, 403

        if request.is_json:
            data = request.json or {}
            report_type = data.get("report_type")
            reporting_month = data.get("reporting_month")
            form_data = data.get("form_data")
        else:
            report_type = request.form.get("report_type")
            reporting_month = request.form.get("reporting_month")
            
            # Construct form_data dictionary from form values
            form_data = {}
            for key in request.form:
                if key in ('report_type', 'reporting_month'):
                    continue
                if key.endswith('[]'):
                    form_data[key] = request.form.getlist(key)
                else:
                    form_data[key] = request.form.get(key)

        if not report_type or not reporting_month or not form_data:
            return {"success": False, "error": "Missing required fields"}, 400

        # Check if report is locked
        cursor.execute("""
            SELECT status FROM signed_reports 
            WHERE username=%s AND reporting_month=%s
        """, (username, reporting_month))
        signed_row = cursor.fetchone()
        if signed_row and signed_row["status"] in ('pending_upload', 'uploaded', 'reviewed'):
            return {"success": False, "error": "This report is locked because the PDF has been generated/submitted. No modifications are allowed."}, 400

        import json
        form_data_str = json.dumps(form_data)

        cursor.execute("""
            INSERT INTO report_drafts (username, report_type, reporting_month, form_data, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (username, report_type, reporting_month)
            DO UPDATE SET form_data = EXCLUDED.form_data, updated_at = CURRENT_TIMESTAMP
        """, (username, report_type, reporting_month, form_data_str))
        conn.commit()

        # If not JSON, save the uploaded workshop files and clean up orphaned ones
        if not request.is_json:
            import os
            import glob
            ws_upload_dir = os.path.join(app.root_path, "static", "signed_reports", "workshop_attachments", username, reporting_month)
            ws_files = request.files.getlist("ws_report_file[]")
            ws_titles = request.form.getlist("ws_title[]")
            num_rows = len(ws_titles)
            
            if num_rows > 0:
                os.makedirs(ws_upload_dir, exist_ok=True)
                for i in range(num_rows):
                    uploaded_file = ws_files[i] if i < len(ws_files) else None
                    if uploaded_file and uploaded_file.filename:
                        # Delete any existing workshop_{i+1}.* files to prevent duplicates
                        for existing in glob.glob(os.path.join(ws_upload_dir, f"workshop_{i+1}.*")):
                            try:
                                os.remove(existing)
                            except Exception:
                                pass
                        ext = os.path.splitext(uploaded_file.filename)[1]
                        save_path = os.path.join(ws_upload_dir, f"workshop_{i+1}{ext}")
                        uploaded_file.save(save_path)
            
            # Clean up orphaned files
            if os.path.exists(ws_upload_dir):
                for f in os.listdir(ws_upload_dir):
                    if f.startswith("workshop_"):
                        try:
                            parts = os.path.splitext(f)[0].split("_")
                            if len(parts) > 1:
                                idx = int(parts[1])
                                if idx > num_rows:
                                    os.remove(os.path.join(ws_upload_dir, f))
                        except Exception:
                            pass

        return {"success": True, "message": "Draft saved successfully!"}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}, 500
    finally:
        conn.close()


# ------------------ IQAC REPORT: VIEW RAW DRAFT DATA ------------------
@app.route("/iqac_report/view_raw/<target_username>/<reporting_month>")
def iqac_report_view_raw(target_username, reporting_month):
    if "username" not in session:
        return redirect("/login")

    logged_user = session["username"]
    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Fetch role of logged-in user to check permissions
    cursor.execute("SELECT * FROM users WHERE username=%s", (logged_user,))
    user_record = cursor.fetchone()

    if not user_record:
        conn.close()
        flash("User not found.", "danger")
        return redirect("/login")

    # Authorize: must be Admin, Secretary, or the target coordinator themselves
    role = user_record["role"].lower()
    if role not in ("admin", "secretary") and logged_user.lower() != target_username.lower():
        conn.close()
        flash("Access denied. You do not have permissions to view this raw data.", "danger")
        return redirect("/dashboard")

    # Fetch target user record (for rendering correct name and campus)
    cursor.execute("SELECT * FROM users WHERE username=%s", (target_username,))
    target_user = cursor.fetchone()
    if not target_user:
        conn.close()
        flash("Target coordinator user not found.", "danger")
        return redirect("/iqac_dashboard" if role not in ("admin", "secretary") else "/admin")

    # Fetch draft raw data
    report_type = "aqar_coordinator" if is_aqar_coordinator(target_user) else "standard"

    cursor.execute("""
        SELECT form_data FROM report_drafts 
        WHERE username=%s AND report_type=%s AND reporting_month=%s
    """, (target_username, report_type, reporting_month))
    draft_row = cursor.fetchone()

    cursor.execute("""
        SELECT status, remarks FROM signed_reports 
        WHERE username=%s AND reporting_month=%s
    """, (target_username, reporting_month))
    signed_row = cursor.fetchone()

    # Scan for existing workshop files
    ws_files_map = {}
    ws_upload_dir = os.path.join(app.root_path, 'static', 'signed_reports', 'workshop_attachments', target_username, reporting_month)
    if os.path.exists(ws_upload_dir):
        for f in os.listdir(ws_upload_dir):
            if f.startswith("workshop_"):
                try:
                    parts = os.path.splitext(f)[0].split("_")
                    if len(parts) > 1:
                        idx = int(parts[1]) - 1
                        ws_files_map[idx] = f
                except Exception:
                    pass

    conn.close()

    if not draft_row:
        flash(f"No raw data found for {target_username.title()} for the month {reporting_month}.", "warning")
        return redirect("/iqac_dashboard" if role not in ("admin", "secretary") else "/admin_signed_reports")

    locked = signed_row is not None and signed_row["status"] in ('pending_upload', 'uploaded', 'reviewed')
    can_unlock = (logged_user.lower() == target_username.lower() and 
                  signed_row is not None and 
                  signed_row["status"] == 'pending_upload')
    rejection_remarks = signed_row["remarks"] if (signed_row and signed_row["status"] == 'corrections_requested') else None

    import json
    draft_data = None
    try:
        draft_data = json.loads(draft_row["form_data"])
    except Exception:
        pass

    try:
        reporting_month_display = datetime.strptime(reporting_month, "%Y-%m").strftime("%m-%Y")
    except Exception:
        reporting_month_display = reporting_month

    if report_type == "aqar_coordinator":
        return render_template("iqac_coordinator_report.html", username=target_username, user=target_user,
                               reporting_month_str=reporting_month,
                               reporting_month_display=reporting_month_display,
                               aqar_coordinator_names=AQAR_COORDINATOR_NAMES,
                               draft_data=draft_data,
                               locked=locked,
                               can_unlock=can_unlock,
                               rejection_remarks=rejection_remarks,
                               ws_files_map=ws_files_map)

    return render_template("iqac_monthly_report.html", username=target_username, user=target_user,
                           reporting_month_str=reporting_month,
                           reporting_month_display=reporting_month_display,
                           draft_data=draft_data,
                           locked=locked,
                           can_unlock=can_unlock,
                           rejection_remarks=rejection_remarks,
                           ws_files_map=ws_files_map)




# ------------------ IQAC REPORT: UNLOCK DRAFT ------------------
@app.route("/iqac_report/unlock/<reporting_month>", methods=["POST"])
def iqac_report_unlock(reporting_month):
    if "username" not in session:
        return redirect("/login")

    username = session["username"]
    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Check current status
    cursor.execute("""
        SELECT status FROM signed_reports
        WHERE username=%s AND reporting_month=%s
    """, (username, reporting_month))
    row = cursor.fetchone()

    if not row:
        conn.close()
        flash("No report found to unlock.", "warning")
        return redirect("/iqac_dashboard")

    status = row["status"]
    if status != 'pending_upload':
        conn.close()
        flash("You cannot unlock this report because it has already been uploaded or reviewed.", "danger")
        return redirect("/iqac_dashboard")

    # Delete from signed_reports to unlock the draft
    try:
        cursor.execute("""
            DELETE FROM signed_reports
            WHERE username=%s AND reporting_month=%s
        """, (username, reporting_month))
        conn.commit()
        flash(f"Report draft for {reporting_month} has been unlocked for editing.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error unlocking report: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect("/iqac_dashboard")


# ------------------ IQAC REPORT: REJECT/REQUEST CORRECTIONS ------------------
@app.route("/admin_reject_report/<int:id>", methods=["POST"])
def admin_reject_report(id):
    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = get_cursor(conn)

    # Check permission
    cursor.execute("SELECT * FROM users WHERE username=%s", (session["username"],))
    admin = cursor.fetchone()

    if not admin or admin["role"].lower() not in ("admin", "secretary"):
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/dashboard")

    # Fetch report to be rejected
    cursor.execute("SELECT * FROM signed_reports WHERE id=%s", (id,))
    report = cursor.fetchone()
    if not report:
        conn.close()
        flash("Report not found.", "danger")
        return redirect("/admin_signed_reports")

    reporting_month = report["reporting_month"]
    target_username = report["username"]

    # Delete from Cloudinary if public_id exists
    if report.get("cloudinary_public_id"):
        cloudinary_delete(report["cloudinary_public_id"])

    remarks = request.form.get("remarks", "").strip()

    # Update status to 'corrections_requested' and save remarks, clearing the uploaded file path
    try:
        cursor.execute("""
            UPDATE signed_reports 
            SET status = 'corrections_requested', remarks = %s, uploaded_file_path = NULL, uploaded_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (remarks, id))
        conn.commit()

        # Send email notification to the coordinator
        notify_coordinator_of_rejection(target_username, reporting_month, remarks)

        flash(f"Correction requested for {target_username.title()}'s report ({reporting_month}). It has been unlocked.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error requesting corrections: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect("/admin_signed_reports")


# ------------------ VIEW SIGNED REPORT (PROXY) ------------------
@app.route("/view_report/<int:report_id>")
def view_report(report_id):
    if 'username' not in session:
        return redirect('/login')

    conn = get_db_connection()
    cursor = get_cursor(conn)
    cursor.execute("SELECT * FROM users WHERE username=%s", (session['username'],))
    user = cursor.fetchone()
    cursor.execute("SELECT * FROM signed_reports WHERE id=%s", (report_id,))
    report = cursor.fetchone()
    conn.close()

    if not user or not report:
        flash("Report not found.", "danger")
        return redirect('/admin_signed_reports')

    role = user['role'].lower()
    is_admin = role in ('admin', 'secretary')
    is_owner = user['username'] == report['username']
    if not is_admin and not is_owner:
        flash("Access denied.", "danger")
        return redirect('/dashboard')

    if not report['uploaded_file_path']:
        flash("No file uploaded for this report.", "danger")
        return redirect('/admin_signed_reports')

    try:
        with urllib.request.urlopen(report['uploaded_file_path']) as resp:
            file_data = resp.read()
        from flask import Response
        download = request.args.get('download') == '1'
        disposition = 'attachment' if download else 'inline'
        filename = f"signed_report_{report['reporting_month']}.pdf"
        return Response(
            file_data,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'{disposition}; filename="{filename}"'}
        )
    except Exception as e:
        flash("Could not load report file.", "danger")
        return redirect('/admin_signed_reports')


# ------------------ IQAC UPLOAD SIGNED REPORT ------------------
ALLOWED_UPLOAD_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}

def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_UPLOAD_EXTENSIONS

@app.route("/iqac_upload_signed_report", methods=["POST"])
def iqac_upload_signed_report():
    if "username" not in session:
        return redirect("/login")

    username = session["username"]
    conn = get_db_connection()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()

    if not user or user["role"].lower() not in ("school iqac coordinator", "campus iqac coordinator"):
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/login")

    # Enforce submission window
    is_open, _, _, _, window_msg = check_submission_window()
    if not is_open:
        conn.close()
        flash("Upload window is currently closed. " + window_msg, "danger")
        return redirect("/iqac_dashboard")

    reporting_month = request.form.get("reporting_month", "").strip()
    uploaded_file = request.files.get("signed_report")

    if not reporting_month:
        flash("Please enter the reporting month.", "danger")
        conn.close()
        return redirect("/iqac_dashboard")

    # Verify that a draft exists before allowing upload
    cursor.execute("""
        SELECT 1 FROM report_drafts 
        WHERE username = %s AND reporting_month = %s
    """, (username, reporting_month))
    if not cursor.fetchone():
        conn.close()
        flash("No report draft found for this month. You must first generate and download the report before uploading the signed copy.", "danger")
        return redirect("/iqac_dashboard")

    if not uploaded_file or uploaded_file.filename == "":
        flash("Please select a file to upload.", "danger")
        conn.close()
        return redirect("/iqac_dashboard")

    if not _allowed_file(uploaded_file.filename):
        flash("Only PDF, JPG, JPEG, or PNG files are allowed.", "danger")
        conn.close()
        return redirect("/iqac_dashboard")

    # Upload to Cloudinary (public_id excludes folder since folder param already sets it)
    public_id = f"{secure_filename(username)}_{reporting_month}"
    try:
        file_url, cld_public_id = cloudinary_upload(uploaded_file, folder="iqac/signed_reports", public_id=public_id, resource_type="raw")
    except Exception as e:
        flash(f"File upload failed: {str(e)}", "danger")
        conn.close()
        return redirect("/iqac_dashboard")

    # Check if a record already exists (e.g. created during PDF download)
    cursor.execute("""
        SELECT * FROM signed_reports
        WHERE username=%s AND reporting_month=%s
    """, (username, reporting_month))
    existing = cursor.fetchone()

    if existing:
        # Delete old Cloudinary file if different public_id
        if existing.get("cloudinary_public_id") and existing["cloudinary_public_id"] != cld_public_id:
            cloudinary_delete(existing["cloudinary_public_id"])
        cursor.execute("""
            UPDATE signed_reports
            SET uploaded_file_path=%s, cloudinary_public_id=%s, status='uploaded', uploaded_at=CURRENT_TIMESTAMP
            WHERE id=%s
        """, (file_url, cld_public_id, existing["id"]))
    else:
        cursor.execute("""
            INSERT INTO signed_reports (username, reporting_month, uploaded_file_path, cloudinary_public_id, status)
            VALUES (%s, %s, %s, %s, 'uploaded')
        """, (username, reporting_month, file_url, cld_public_id))
        
    conn.commit()
    conn.close()

    # Notify all admins and secretaries
    try:
        notify_conn = get_db_connection()
        notify_cur = get_cursor(notify_conn)
        notify_cur.execute("SELECT email FROM users WHERE role IN ('Admin', 'Secretary') AND email IS NOT NULL AND email != ''")
        recipients = notify_cur.fetchall()
        notify_conn.close()

        reporting_month_display = datetime.strptime(reporting_month, "%Y-%m").strftime("%m-%Y")
        subject = f"IQAC Report Submitted – {username.title()} ({reporting_month_display})"
        body = (
            f"Dear Admin/Secretary,\n\n"
            f"{username.title()} ({user.get('designation', '')}, {user.get('department', '')}) "
            f"has submitted their signed IQAC report for {reporting_month_display}.\n\n"
            f"Please log in to review and authorise the report.\n\n"
            f"Regards,\nIQAC Worklog System"
        )
        for r in recipients:
            try:
                send_email(r['email'], subject, body)
            except Exception as e:
                print(f"Failed to notify {r['email']}: {e}")
    except Exception as e:
        print(f"Notification error: {e}")

    flash("Signed report uploaded successfully! It will be reviewed by the admin.", "success")
    return redirect("/iqac_dashboard")


# ------------------ ADMIN: VIEW SIGNED REPORTS ------------------
@app.route("/admin_signed_reports")
def admin_signed_reports():
    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM users WHERE username=%s", (session["username"],))
    admin = cursor.fetchone()

    if not admin or admin["role"].lower() not in ("admin", "secretary"):
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/dashboard")

    # Default to previous month (reports submitted in early current month cover last month)
    now = datetime.now()
    if now.month == 1:
        default_month = f"{now.year - 1}-12"
    else:
        default_month = f"{now.year}-{now.month - 1:02d}"
    selected_month = request.args.get("month", default_month)

    cursor.execute("""
        SELECT sr.*, u.designation, u.department, u.full_name
        FROM signed_reports sr
        JOIN users u ON sr.username = u.username
        WHERE sr.reporting_month = %s AND sr.status != 'pending_upload'
        ORDER BY sr.uploaded_at DESC
    """, (selected_month,))
    reports = cursor.fetchall()
    conn.close()

    # Query workshop attachments from DB (Cloudinary URLs)
    conn2 = get_db_connection()
    cursor2 = get_cursor(conn2)
    cursor2.execute("""
        SELECT username, filename, cloudinary_url, workshop_index
        FROM workshop_attachment_files
        WHERE reporting_month = %s
        ORDER BY username, workshop_index
    """, (selected_month,))
    ws_rows = cursor2.fetchall()
    conn2.close()
    workshop_attachments = {}
    for row in ws_rows:
        uname = row["username"]
        if uname not in workshop_attachments:
            workshop_attachments[uname] = []
        workshop_attachments[uname].append({'name': row["filename"], 'url': row["cloudinary_url"]})

    return render_template("admin_signed_reports.html",
        username=session["username"],
        reports=reports,
        selected_month=selected_month,
        workshop_attachments=workshop_attachments
    )


@app.route("/workshop_attachments")
def public_workshop_attachments():
    """Public listing of workshop attachments for a selected month.
    Accessible to any logged-in user so they can view or download attachments.
    """
    if "username" not in session:
        return redirect("/login")

    # Default to previous month as used elsewhere
    now = datetime.now()
    if now.month == 1:
        default_month = f"{now.year - 1}-12"
    else:
        default_month = f"{now.year}-{now.month - 1:02d}"
    selected_month = request.args.get("month", default_month)

    ws_conn = get_db_connection()
    ws_cur = get_cursor(ws_conn)
    ws_cur.execute("""
        SELECT username, filename, cloudinary_url, workshop_index
        FROM workshop_attachment_files
        WHERE reporting_month = %s
        ORDER BY username, workshop_index
    """, (selected_month,))
    workshop_attachments = {}
    for row in ws_cur.fetchall():
        uname = row["username"]
        if uname not in workshop_attachments:
            workshop_attachments[uname] = []
        workshop_attachments[uname].append({'name': row["filename"], 'url': row["cloudinary_url"]})
    ws_conn.close()

    return render_template('workshop_attachments.html',
        username=session['username'],
        selected_month=selected_month,
        workshop_attachments=workshop_attachments
    )


@app.route("/admin_review_report/<int:id>", methods=["POST"])
def admin_review_report(id):
    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM users WHERE username=%s", (session["username"],))
    admin = cursor.fetchone()

    if not admin or admin["role"].lower() not in ("admin", "secretary"):
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/dashboard")

    cursor.execute("UPDATE signed_reports SET status='reviewed' WHERE id=%s", (id,))
    conn.commit()
    conn.close()

    flash("Report marked as reviewed.", "success")
    return redirect("/admin_signed_reports")


# ------------------ SECRETARY DASHBOARD ------------------
@app.route("/secretary_dashboard", methods=["GET", "POST"])
def secretary_dashboard():
    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = get_cursor(conn)
    cursor.execute("SELECT * FROM users WHERE username=%s", (session["username"],))
    user = cursor.fetchone()

    if not user or user["role"].lower() != "secretary":
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/login")

    now = datetime.now()
    prev = now.replace(day=1) - timedelta(days=1)
    current_report_month = prev.strftime("%Y-%m")

    cursor.execute("SELECT COUNT(*) as count FROM users WHERE role IN ('School IQAC Coordinator', 'Campus IQAC Coordinator')")
    total_coordinators = cursor.fetchone()['count']

    cursor.execute("""
        SELECT COUNT(DISTINCT sr.username) as count FROM signed_reports sr
        JOIN users u ON sr.username = u.username
        WHERE sr.reporting_month = %s
        AND sr.status IN ('uploaded', 'reviewed')
        AND u.role IN ('School IQAC Coordinator', 'Campus IQAC Coordinator')
    """, (current_report_month,))
    submitted_coordinators = cursor.fetchone()['count']

    submission_pct = int((submitted_coordinators / total_coordinators * 100) if total_coordinators > 0 else 0)

    cursor.execute("""
        SELECT DISTINCT u.username, u.full_name FROM users u
        JOIN signed_reports sr ON sr.username = u.username
        WHERE u.role IN ('School IQAC Coordinator', 'Campus IQAC Coordinator')
        AND sr.reporting_month = %s AND sr.status IN ('uploaded', 'reviewed')
    """, (current_report_month,))
    submitted_coordinator_names = [r['full_name'] or r['username'] for r in cursor.fetchall()]

    cursor.execute("""
        SELECT DISTINCT u.username, u.full_name FROM users u
        JOIN signed_reports sr ON sr.username = u.username
        WHERE u.role IN ('School IQAC Coordinator', 'Campus IQAC Coordinator')
        AND sr.reporting_month = %s AND sr.status IN ('pending_upload', 'corrections_requested')
    """, (current_report_month,))
    draft_coordinator_names = [r['full_name'] or r['username'] for r in cursor.fetchall()]

    cursor.execute("""
        SELECT username, full_name FROM users WHERE role IN ('School IQAC Coordinator', 'Campus IQAC Coordinator')
        AND username NOT IN (
            SELECT DISTINCT username FROM signed_reports WHERE reporting_month = %s
        )
    """, (current_report_month,))
    pending_coordinators = [r['full_name'] or r['username'] for r in cursor.fetchall()]

    # Coordinators list for Quick Summary dropdown
    cursor.execute("SELECT username, role FROM users WHERE role IN ('School IQAC Coordinator', 'Campus IQAC Coordinator') ORDER BY username")
    coordinators = cursor.fetchall()

    # Quick Summary form handling
    coord_reports = None
    coord_user = "All"
    coord_report_type = "monthly"
    coord_from_month = f"{now.year}-01"
    coord_to_month = f"{now.year}-{now.month:02d}"
    coord_year = str(now.year)

    if request.method == "POST" and "coord_form" in request.form:
        coord_user = request.form.get("coord_user", "All")
        coord_report_type = request.form.get("coord_report_type", "monthly")
        coord_from_month = request.form.get("coord_from_month", f"{now.year}-01")
        coord_to_month = request.form.get("coord_to_month", f"{now.year}-{now.month:02d}")
        coord_year = request.form.get("coord_year", str(now.year))

        year_int = int(coord_year)
        if coord_report_type == "yearly":
            start_m = f"{year_int}-01"
            end_m = f"{year_int}-12"
        else:
            start_m = coord_from_month or f"{year_int}-01"
            end_m = coord_to_month or f"{year_int}-{now.month:02d}"

        if coord_user == "All":
            cursor.execute("""
                SELECT sr.*, u.designation, u.department, u.role
                FROM signed_reports sr
                JOIN users u ON sr.username = u.username
                WHERE sr.reporting_month BETWEEN %s AND %s
                ORDER BY sr.reporting_month, sr.username
            """, (start_m, end_m))
        else:
            cursor.execute("""
                SELECT sr.*, u.designation, u.department, u.role
                FROM signed_reports sr
                JOIN users u ON sr.username = u.username
                WHERE sr.username = %s AND sr.reporting_month BETWEEN %s AND %s
                ORDER BY sr.reporting_month
            """, (coord_user, start_m, end_m))
        coord_reports = cursor.fetchall()

    conn.close()

    return render_template("secretary_dashboard.html",
        username=session["username"],
        current_report_month=current_report_month,
        total_coordinators=total_coordinators,
        submitted_coordinators=submitted_coordinators,
        submission_pct=submission_pct,
        pending_coordinators=pending_coordinators,
        submitted_coordinator_names=submitted_coordinator_names,
        draft_coordinator_names=draft_coordinator_names,
        coordinators=coordinators,
        coord_reports=coord_reports,
        coord_user=coord_user,
        coord_report_type=coord_report_type,
        coord_from_month=coord_from_month,
        coord_to_month=coord_to_month,
        coord_year=coord_year,
    )


# ------------------ SCHEDULER ------------------
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()

# Daily at 6 PM — sends report submission reminder to coordinators who haven't submitted (days 1–5 of month)
scheduler.add_job(send_auto_iqac_reminders, 'cron', hour=18, minute=0, id='iqac_report_reminder')

# 29th of every month at 9 AM — worklog missing entries reminder to employees
scheduler.add_job(send_29th_reminder, 'cron', day=29, hour=9, minute=0, id='worklog_29th_reminder')

# 1st of every month at 9 AM — final worklog deadline reminder to employees
scheduler.add_job(send_1st_deadline_reminder, 'cron', day=1, hour=9, minute=0, id='worklog_1st_reminder')

scheduler.start()


# ------------------ RUN APP ------------------
if __name__ == "__main__":
    app.run(debug=True)
