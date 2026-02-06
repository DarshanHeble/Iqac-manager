from flask import Flask, render_template, request, redirect, url_for, flash, session
import os, random, string, smtplib, json
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from werkzeug.security import generate_password_hash, check_password_hash
import calendar
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
import google.generativeai as genai

# Load environment variables from .env file (override any existing env vars)
load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")

# Make datetime available in all templates
app.jinja_env.globals['datetime'] = datetime

# Add context processor for current year in footer
@app.context_processor
def inject_now():
    return {'now': datetime.now}

# ------------------ DATABASE CONFIGURATION (PostgreSQL) ------------------
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Get PostgreSQL database connection"""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set. Please configure your PostgreSQL connection in .env file.")
    
    # Handle both postgres:// and postgresql:// URLs (Render uses postgres://)
    db_url = DATABASE_URL
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    # Try with SSL first (for cloud databases like Render, Supabase, etc.)
    try:
        conn = psycopg2.connect(db_url, sslmode="require")
        return conn
    except psycopg2.OperationalError:
        # Fallback to no SSL for local PostgreSQL
        try:
            conn = psycopg2.connect(db_url, sslmode="prefer")
            return conn
        except psycopg2.OperationalError:
            # Last attempt with no SSL at all
            conn = psycopg2.connect(db_url, sslmode="disable")
            return conn

def get_cursor(conn):
    """Get cursor for PostgreSQL database"""
    return conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

# ------------------ EMAIL SETTINGS (Environment Variables) ------------------
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# ------------------ EMAIL REMINDER FUNCTIONS ------------------
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
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = SMTP_EMAIL
        msg['To'] = to_email
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
        return True
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
    
    # Get all non-admin users
    cursor.execute("SELECT username, email FROM users WHERE role != 'admin'")
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
            deadline_str = deadline_date.strftime('%b %d, %Y')
            
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
    
    # Get all non-admin users
    cursor.execute("SELECT username, email FROM users WHERE role != 'admin'")
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
            deadline_str = today.strftime('%b %d, %Y')
            
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
if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
    genai.configure(api_key=GEMINI_API_KEY)

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
            role VARCHAR(50)
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
            task TEXT
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

# ------------------ TEMPLATE FILTER ------------------

# ------------------ TEMPLATE FILTER ------------------
@app.template_filter("datetimeformat")
def datetimeformat(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
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
            flash(f"Welcome, {username}!", "success")
            return redirect("/admin") if user["role"].lower() == "admin" else redirect("/dashboard")
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
                        # Store categories as comma-separated and tasks as JSON
                        category_str = ", ".join(category_tasks.keys())
                        task_json = json.dumps(category_tasks)
                        
                        cursor.execute("""
                            INSERT INTO worklog (username, date, status, category, task)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (username, date_iso, "Present", category_str, task_json))
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

    # Fetch users for dropdown
    cursor.execute("SELECT username, emp_id FROM users WHERE role!='Admin'")
    users = cursor.fetchall()

    # Get stats for dashboard cards
    cursor.execute("SELECT COUNT(*) FROM users WHERE role != 'Admin'")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM worklog")
    total_entries = cursor.fetchone()[0]

    # This month's entries
    now = datetime.now()
    month_start = f"{now.year}-{now.month:02d}-01"
    month_end = f"{now.year}-{now.month:02d}-{calendar.monthrange(now.year, now.month)[1]}"
    cursor.execute("SELECT COUNT(*) FROM worklog WHERE date BETWEEN %s AND %s", (month_start, month_end))
    month_entries = cursor.fetchone()[0]

    # Initialize filter variables
    filter_mode = "month"
    selected_month = datetime.now().strftime("%Y-%m")
    from_date = None
    to_date = None
    selected_academic_year = None
    selected_user = "All"
    category_filter = "All"

    # Get filter values from form
    if request.method == "POST":
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
        display_month = datetime.strptime(selected_month, "%Y-%m").strftime("%B %Y")
    except:
        display_month = datetime.now().strftime("%B %Y")

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
        month_entries=month_entries
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
                INSERT INTO users (username, password, emp_id, email, gender, designation, department, role)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (username, hashed, emp_id, email, gender, designation, department, role))
            conn.commit()

            # Send credentials email
            try:
                msg = MIMEText(f"""
Dear {username},

Your IQAC Worklog account has been created.

Username: {username}
Password: {password}

Login: https://iqacworklog.christuniversity.in/login

Regards,
IQAC Admin
""")
                msg["Subject"] = "IQAC Worklog Account Created"
                msg["From"] = SMTP_EMAIL
                msg["To"] = email

                with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                    server.starttls()
                    server.login(SMTP_EMAIL, SMTP_PASSWORD)
                    server.send_message(msg)

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
        msg = MIMEText(f"""
    Dear {username},

    Your password for the IQAC Worklog account has been successfully reset. Please find your updated login credentials below:

    Username: {username}
    New Password: {new_password}

    You may log in using the following link:
    https://iqacworklog.christuniversity.in

    If you did not request this reset or require any assistance, please contact the admin.

    Regards,
    IQAC Admin
    """)

        msg["Subject"] = "IQAC Worklog Password Reset"
        msg["From"] = SMTP_EMAIL
        msg["To"] = email

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)

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

    # Ensure admin
    cursor.execute("SELECT * FROM users WHERE username=%s", (session["username"],))
    admin = cursor.fetchone()

    if not admin or admin["role"].lower() != "admin":
        conn.close()
        flash("Access denied.", "danger")
        return redirect("/dashboard")

    # Fetch users
    cursor.execute("SELECT username, emp_id FROM users WHERE role!='Admin'")
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
    cursor.execute("SELECT username, emp_id FROM users WHERE role!='Admin'")
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
                # List available models to find the correct one
                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                if not available_models:
                    ai_error = "No compatible Gemini models found."
                else:
                    # Use the first available model
                    model_name = available_models[0]
                    model = genai.GenerativeModel(model_name)
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
                    response = model.generate_content(prompt)
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
                designation=%s, department=%s, role=%s WHERE id=%s
            """, (new_username, emp_id, email, gender, designation, department, role, id))

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
        msg = MIMEText(f"""
    Dear {user['username']},

    Your password for the IQAC Worklog account has been successfully reset. Please find your updated login credentials below:

    Username: {user['username']}
    New Password: {new_password}

    You may log in using the following link:
    https://iqacworklog.christuniversity.in

    If you did not request this reset or require any assistance, please contact the admin.

    Regards,
    IQAC Admin
    """)
        msg["Subject"] = "IQAC Worklog - Password Reset"
        msg["From"] = SMTP_EMAIL
        msg["To"] = user["email"]

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)

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
        return f"Not the 29th. Today is {today.strftime('%d/%m/%Y')}", 400
    
    result = send_29th_reminder()
    return result, 200

@app.route("/send_1st_deadline_reminders")
def trigger_1st_deadline_reminders():
    """Trigger 1st deadline reminder emails - can be called by scheduler"""
    today = datetime.now().date()
    
    # Only send on 1st of the month
    if today.day != 1:
        return f"Not the 1st. Today is {today.strftime('%d/%m/%Y')}", 400
    
    result = send_1st_deadline_reminder()
    return result, 200

# ------------------ RUN APP ------------------
if __name__ == "__main__":
    app.run(debug=True)
