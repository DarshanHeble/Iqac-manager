===============================================
IQAC Worklog Management System
===============================================

A comprehensive Flask-based web application for managing and tracking daily work activities 
for the Internal Quality Assurance Cell (IQAC) at Christ University.

===============================================
OVERVIEW
===============================================

This application provides a role-based worklog management system where:
- Administrators can manage users, view consolidated reports, and oversee all activities
- Employees can log their daily tasks, categorize work, and generate personal reports
- Real-time data visualization with Chart.js pie charts
- Email notifications for password resets and user management
- Export and print functionality for reports

===============================================
FEATURES
===============================================

Admin Features:
- User Management (Add, Edit, Delete users)
- Generate reports for individual or all employees
- View consolidated statistics and analytics
- Reset user passwords with email notifications
- Monitor all worklog entries across the organization

Employee Features:
- Daily task entry with multiple categories
- Bulleted task descriptions with rich formatting
- Personal worklog history and reports
- Monthly statistics dashboard
- Chart.js visualizations for work distribution
- Export and print personal reports

===============================================
ARCHITECTURE
===============================================

Technology Stack:
- Backend: Python 3.10+ with Flask 3.0
- Database: PostgreSQL (production) with automatic initialization
- Frontend: Bootstrap 5, jQuery, Select2 (local assets)
- Visualization: Chart.js for data analytics
- Security: Werkzeug password hashing, session management
- Email: SMTP integration for notifications

Database Schema:
1. users table:
   - id, username, password (hashed), emp_id, email
   - gender, designation, department, role (Admin/Employee)

2. worklog table:
   - id, username, date, status, category, task (JSON)
   - Indexed on username and date for performance

Application Structure:
├── app.py                  # Main Flask application
├── templates/              # HTML templates
│   ├── login.html         # Login page
│   ├── admin.html         # Admin dashboard
│   ├── dashboard.html     # Employee dashboard
│   ├── user_add_entry.html
│   ├── user_view_entries.html
│   ├── user_report.html
│   ├── admin_manage_users.html
│   ├── admin_add_user.html
│   ├── admin_edit_user.html
│   └── admin_report.html
├── static/                 # Static assets
│   ├── chart.js           # Chart.js library
│   ├── select2.js/.css    # Select2 dropdown library
│   └── christ_logo.png    # University logo
├── logo/                   # Logo assets
├── requirements.txt        # Python dependencies
├── Procfile               # Deployment configuration
└── .env                   # Environment variables (not in repo)

===============================================
SETUP & INSTALLATION
===============================================

1. Prerequisites:
   - Python 3.10 or higher
   - PostgreSQL database server
   - Git

2. Clone the repository:
   git clone https://github.com/vvaish0987/Iqac-work-log.git
   cd Iqac-work-log

3. Create virtual environment (recommended):
   python -m venv venv
   
   # Windows:
   venv\Scripts\activate
   
   # Linux/Mac:
   source venv/bin/activate

4. Install dependencies:
   pip install -r requirements.txt

5. Database Setup:
   a. Install PostgreSQL from https://www.postgresql.org/download/
   b. Create database:
      psql -U postgres
      CREATE DATABASE iqac_worklog;
      \q

6. Configure Environment Variables:
   Create a .env file in the project root with the following:

   DATABASE_URL=postgresql://postgres:123456@localhost:5432/iqac_worklog
   SECRET_KEY=your_secret_key_here
   SMTP_EMAIL=associatedirector.iqac@christuniversity.in
   SMTP_PASSWORD=sbjeumibabhrvyhs

7. Run the application:
   python app.py

8. Access the application:
   Open your browser and navigate to: http://127.0.0.1:5000

===============================================
CREDENTIALS
===============================================

Default Admin Account:
- Username: admin
- Password: admin123
- Email: admin@university.edu
- Employee ID: CU0001
- Role: Admin/Director, IQAC

Database Credentials:
- Database: iqac_worklog
- User: postgres
- Password: 123456
- Host: localhost
- Port: 5432

Email Configuration:
- SMTP Server: smtp.gmail.com
- Port: 587
- Email: associatedirector.iqac@christuniversity.in
- App Password: sbjeumibabhrvyhs

Note: For Gmail, ensure:
1. 2-Factor Authentication is enabled
2. App Password is generated at https://myaccount.google.com/apppasswords

===============================================
APPLICATION WORKFLOW
===============================================

1. Authentication Flow:
   - User logs in with username/password
   - System validates credentials against PostgreSQL database
   - Session is created with role-based access
   - Redirect to Admin or Employee dashboard based on role

2. Employee Workflow:
   - Access dashboard showing monthly statistics
   - Add new worklog entry with date, status, and categories
   - Select multiple categories (Teaching, Research, Admin, etc.)
   - Add bulleted tasks for each category
   - View/Edit/Delete previous entries
   - Generate and export personal reports

3. Admin Workflow:
   - View consolidated dashboard with all user statistics
   - Manage users (Add/Edit/Delete)
   - Generate individual or organization-wide reports
   - Reset user passwords (sends email notification)
   - Monitor all worklog activities

4. Data Persistence:
   - All entries stored in PostgreSQL database
   - Automatic table creation on first run
   - Indexed queries for optimal performance
   - Session management for security

===============================================
DEPLOYMENT
===============================================

For production deployment on Render/Heroku:

1. Update DATABASE_URL in environment variables
2. Set production SECRET_KEY (generate secure random string)
3. Configure SMTP settings for email notifications
4. Use gunicorn as WSGI server (included in requirements.txt)
5. Procfile is included for automatic deployment

===============================================
DEPENDENCIES
===============================================

- Flask==3.0.0          # Web framework
- Werkzeug==3.0.1       # WSGI utilities
- psycopg2-binary==2.9.9 # PostgreSQL adapter
- gunicorn==21.2.0      # Production WSGI server
- python-dotenv==1.0.1  # Environment variable management

===============================================
SECURITY FEATURES
===============================================

- Password hashing using Werkzeug security
- Session-based authentication
- Role-based access control (RBAC)
- SQL injection prevention with parameterized queries
- Environment variable protection (.env not in repository)
- CSRF protection via Flask sessions
- Cache-control headers to prevent sensitive data caching

===============================================
SUPPORT & MAINTENANCE
===============================================

For issues or questions:
- GitHub: https://github.com/vvaish0987/Iqac-work-log
- Email: associatedirector.iqac@christuniversity.in

===============================================
LICENSE
===============================================

Copyright © 2026 Christ University - IQAC
All rights reserved.
