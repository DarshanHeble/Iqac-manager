Worklog Application - Admin Update (Development Mode)
==================================================

This application is a Flask-based IQAC Worklog Management System.

Features
--------
- Role-based login (Admin / Employee)
- Multi-category & bulleted task entry
- Admin can generate reports for one or all employees (printable, no saved PDF)
- Chart.js IQAC-themed Pie Chart
- Add user functionality (default password 'user123')
- Bootstrap 5 + Select2 (local assets)
- Auto-created SQLite database with demo data

Demo Users
-----------
- Admin: admin / admin123
- John Doe: johndoe / user123
- Sara Smith: sarasmith / user123

Run Instructions
----------------
1. Create virtual environment (optional):
   python -m venv venv
   venv\Scripts\activate (Windows) or source venv/bin/activate (Linux/Mac)

2. Install dependencies:
   pip install flask reportlab

3. Run the app:
   python app.py

4. Open http://127.0.0.1:5000 in browser.

Environment
------------
- Python 3.10+
- Flask 3.0.x
- ReportLab 4.1.x

Files Included
---------------
- app.py
- templates/login.html
- templates/dashboard.html
- templates/report_view.html
- static/chart.js
- static/select2.js
- static/select2.css
- worklog.db
- sample_all_report.html
- README.txt
