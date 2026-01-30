from flask import Flask, render_template, request, redirect, url_for, flash, session
import os, random, string, smtplib, json, sqlite3
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from werkzeug.security import generate_password_hash, check_password_hash
import calendar
from dotenv import load_dotenv

# Load environment variables from .env file (override any existing env vars)
load_dotenv(override=True)

# Try to import psycopg2 for PostgreSQL support
try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")

# Make datetime available in all templates
app.jinja_env.globals['datetime'] = datetime

# Add context processor for current year in footer
@app.context_processor
def inject_now():
    return {'now': datetime.now}

# ------------------ DATABASE CONFIGURATION ------------------
DATABASE_URL = os.getenv("DATABASE_URL")
USE_SQLITE = not DATABASE_URL or not PSYCOPG2_AVAILABLE

def get_db_connection():
    """Get database connection (SQLite or PostgreSQL)"""
    if USE_SQLITE:
        # Use SQLite as fallback
        conn = sqlite3.connect("iqac_worklog.db")
        conn.row_factory = sqlite3.Row
        return conn
    else:
        # Use PostgreSQL
        db_url = DATABASE_URL
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        
        # Try with SSL first (for cloud databases)
        try:
            conn = psycopg2.connect(db_url, sslmode="require")
            return conn
        except psycopg2.OperationalError:
            try:
                conn = psycopg2.connect(db_url, sslmode="prefer")
                return conn
            except psycopg2.OperationalError:
                conn = psycopg2.connect(db_url, sslmode="disable")
                return conn

class CursorWrapper:
    """Wrapper to handle both SQLite (?) and PostgreSQL (%s) parameter styles"""
    def __init__(self, cursor, is_sqlite=False):
        self.cursor = cursor
        self.is_sqlite = is_sqlite
    
    def execute(self, query, params=()):
        if self.is_sqlite:
            # Convert %s to ? for SQLite
            query = query.replace('%s', '?')
        return self.cursor.execute(query, params)
    
    def fetchone(self):
        result = self.cursor.fetchone()
        # Convert sqlite3.Row to dict for consistency
        if self.is_sqlite and result:
            return dict(result)
        return result
    
    def fetchall(self):
        results = self.cursor.fetchall()
        # Convert sqlite3.Row to dict for consistency
        if self.is_sqlite and results:
            return [dict(row) for row in results]
        return results
    
    def __getattr__(self, name):
        # Delegate other attributes to the wrapped cursor
        return getattr(self.cursor, name)

def get_cursor(conn):
    """Get cursor appropriate for the database type"""
    if USE_SQLITE:
        return CursorWrapper(conn.cursor(), is_sqlite=True)
    else:
        return CursorWrapper(conn.cursor(cursor_factory=psycopg2.extras.DictCursor), is_sqlite=False)

# ------------------ EMAIL SETTINGS (Environment Variables) ------------------
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# ------------------ DISABLE CACHING ------------------
@app.after_request
def disable_cache(resp):
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

# ------------------ INIT DATABASE ------------------
def init_sqlite():
    """Initialize SQLite database with tables and default admin"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            emp_id TEXT,
            email TEXT,
            gender TEXT,
            designation TEXT,
            department TEXT,
            role TEXT
        )
    """)

    # Create worklog table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS worklog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            date TEXT,
            status TEXT,
            category TEXT,
            task TEXT
        )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_worklog_username ON worklog(username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_worklog_date ON worklog(date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)")

    # Default admin
    cursor.execute("SELECT * FROM users WHERE username='admin'")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO users (username, password, emp_id, email, gender, designation, department, role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
    if USE_SQLITE:
        print("Using SQLite database (iqac_worklog.db)")
        init_sqlite()
    else:
        print("Using PostgreSQL database")
        init_postgres()
except Exception as e:
    print(f"Warning: Could not initialize database: {e}")

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
                    flash("Worklog entry added successfully!", "success")
                    conn.close()
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

Login: http://127.0.0.1:5000/login

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
Your password has been reset.

Username: {username}
New Password: {new_password}

Login: http://127.0.0.1:5000/login
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

Your password has been reset by the administrator.

Username: {user['username']}
New Password: {new_password}

Login: http://127.0.0.1:5000/login

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


# ------------------ RUN APP ------------------
if __name__ == "__main__":
    app.run(debug=True)
