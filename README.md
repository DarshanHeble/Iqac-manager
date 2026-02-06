# IQAC Worklog Management System

A comprehensive Flask-based worklog management system for CHRIST (Deemed to be University)'s Internal Quality Assurance Cell (IQAC). This system allows employees to log their work activities, tracks completion status, generates reports, and uses AI to summarize work activities.

## Features

### 👤 User Management
- **User Registration & Login**: Secure authentication with hashed passwords
- **Dual Role Support**: Admin and Employee roles
- **User Profiles**: Employee ID, Email, Gender, Designation, Department tracking
- **Password Recovery**: Forgot password functionality with email reset links

### 📝 Worklog Entry Management
- **Add Worklog Entries**: Log work activities for specific dates with category-wise tasks
- **Categories**: 
  - Documentation and Audits
  - Rankings
  - Publications
  - Training and Development
  - Strategic Initiatives
  - Others

- **Special Entry Types**:
  - **Holiday**: Mark days as holidays
  - **Leave**: Mark days as leave
  - Categories automatically disable when holiday/leave is selected

- **Working Day Restrictions**:
  - Sundays are non-working days (blocked)
  - 3rd Saturday of each month is non-working day (blocked)
  - Date validation prevents entries on non-working days

- **Date Entry Rules**:
  - Can only add entries for current month after 2nd
  - Previous month entries allowed until 2nd of current month
  - Cannot add entries for future dates
  - Last 7 days editable after entry

### 📊 Report Generation
- **Admin Report** (`/admin_report`):
  - View worklog entries for all users or specific user
  - Filter by category
  - Three report types:
    - Custom Date Range
    - Month-wise reporting
    - Academic Year (May-April)
  - Export to print with professional formatting
  - Professional IQAC header in print view

- **User Report** (`/user_report`):
  - Employees can view their own worklog summary
  - Same filtering options as admin report
  - Print-friendly format

- **View Entries** (`/user_view_entries`):
  - Employees can browse their worklog entries
  - Category-wise task display
  - Edit/Delete options for recent entries

### 🤖 AI-Powered Summary (Gemini API)
- **AI Report Generation** (`/admin_report_ai`):
  - Generate intelligent summaries of worklog data using Google Gemini AI
  - Same filtering options as regular reports
  - Analyzes work patterns, key activities, and trends
  - Plain text format (no markdown)
  - Professional formatting suitable for official reports

- **Quick AI Summary Button**: Header button for quick access to AI summaries

### 📧 Automated Email Reminders
- **29th of Month Reminder**:
  - Sent to all employees at 9 AM
  - Lists all missing worklog entries for current month
  - Reminds deadline is 2nd of next month at midnight

- **1st of Month Deadline Reminder**:
  - Sent to all employees at 9 AM
  - URGENT reminder about previous month entries
  - Lists missing entries with URGENT tone
  - Deadline is TODAY midnight

- **Test Email Feature** (`/admin_send_test_reminder`):
  - Admin can send test emails to specific users
  - Test both 29th and 1st reminder formats
  - Verify email system is working before automation

### 📅 Date Formatting
- Consistent DD/MM/YYYY format throughout application
- Applied to all date displays in reports and entries
- Matches university's preferred date format

### 🖨️ Print Optimization
- Professional print styles for all reports
- Removes design elements when printing
- Plain tables with black borders for clarity
- IQAC header with logo in print view
- Suitable for official documentation

## Technology Stack

### Backend
- **Framework**: Flask 3.0.0
- **Database**: PostgreSQL
- **Database Driver**: psycopg2-binary 2.9.9
- **Python Version**: 3.14+
- **Task Scheduling**: APScheduler (optional)
- **Email**: smtplib (SMTP)

### Frontend
- **CSS Framework**: Bootstrap 5.3.2
- **Icons**: Bootstrap Icons 1.10.5
- **JavaScript**: Vanilla JS (no external dependencies)
- **Template Engine**: Jinja2

### AI Integration
- **AI Service**: Google Generative AI (Gemini)
- **Library**: google-generativeai 0.8.6
- **Model**: Auto-detected from available models
- **Purpose**: Summarize and analyze work activities

## Installation

### Prerequisites
- Python 3.14+
- PostgreSQL 12+
- Gmail account with App-Specific Password (for email reminders)
- Google Gemini API Key (for AI summaries)

### Setup Steps

1. **Clone the repository**:
```bash
git clone https://github.com/yourusername/iqac-worklog.git
cd iqac-worklog
```

2. **Create virtual environment**:
```bash
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Configure environment variables** (`.env` file):
```
DATABASE_URL=postgresql://username:password@localhost:5432/iqac_worklog
SECRET_KEY=your_secret_key_here
SMTP_EMAIL=your-email@gmail.com
SMTP_PASSWORD=your-app-specific-password
GEMINI_API_KEY=your_gemini_api_key
```

5. **Create database** (if not exists):
```bash
# Using psql
createdb iqac_worklog
```

6. **Run the application**:
```bash
python app.py
```

Access the application at: `https://iqacworklog.christuniversity.in`

## Configuration

### Gmail SMTP Setup
1. Enable 2-Factor Authentication on your Gmail account
2. Generate App-Specific Password: https://myaccount.google.com/apppasswords
3. Use the generated password in `.env` as `SMTP_PASSWORD`

### Google Gemini API Setup
1. Get API key from: https://aistudio.google.com/app/apikey
2. Add to `.env` as `GEMINI_API_KEY`
3. No additional setup required - system auto-detects available models

### Email Reminder Scheduler

#### Option 1: Windows Task Scheduler
See [SCHEDULER_SETUP.md](./SCHEDULER_SETUP.md) for detailed instructions on scheduling automated emails.

#### Option 2: APScheduler (Built-in)
Add to `app.py` (optional):
```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(send_29th_reminder, 'cron', day=29, hour=9, minute=0)
scheduler.add_job(send_1st_deadline_reminder, 'cron', day=1, hour=9, minute=0)
scheduler.start()
```

## Usage

### For Employees
1. **Login**: Enter credentials
2. **Dashboard**: View recent entries and quick stats
3. **Add Entry**: 
   - Navigate to "Add Entry"
   - Select date (calendar picker)
   - Optional: Check "Holiday" or "Leave"
   - Select categories and enter tasks
   - Submit
4. **View Entries**: Browse past entries, edit recent ones (within 7 days)
5. **Generate Report**: Create custom worklog summaries with filters

### For Administrators
1. **Login**: Admin credentials
2. **Dashboard**: View system statistics
3. **Manage Users**: Add, edit, delete employee accounts
4. **Admin Report**: 
   - Generate worklog reports for all users or specific users
   - Filter by category and date range
   - View detailed task breakdowns
   - Print professional reports
5. **AI Summary Report**:
   - Generate AI-powered summaries of work activities
   - Analyze trends and patterns
   - Export for official documentation
6. **Test Email Reminders**: 
   - Navigate to "Send Test Reminders"
   - Select user and reminder type (29th or 1st)
   - Verify email system is working

## API Endpoints

### Authentication
- `GET/POST /login` - User login
- `GET/POST /register` - User registration
- `POST /logout` - User logout
- `GET/POST /forgot` - Password recovery

### User Routes
- `GET /dashboard` - User dashboard
- `GET/POST /user_add_entry` - Add worklog entry
- `GET /user_view_entries` - View own entries
- `GET/POST /edit/<id>` - Edit entry
- `POST /delete_entry/<id>` - Delete entry
- `GET/POST /user_report` - Generate personal report

### Admin Routes
- `GET /admin` - Admin dashboard
- `GET/POST /admin_report` - Generate worklog report
- `GET/POST /admin_report_ai` - Generate AI summary report
- `GET /admin_manage_users` - Manage users
- `GET/POST /admin_add_user` - Add user
- `GET/POST /admin_edit_user/<id>` - Edit user
- `POST /admin_delete_user/<id>` - Delete user
- `GET/POST /admin_send_test_reminder` - Send test emails

### Scheduler Routes (Optional)
- `GET /send_29th_reminders` - Trigger 29th reminders (use with scheduler)
- `GET /send_1st_deadline_reminders` - Trigger 1st reminders (use with scheduler)

## Database Schema

### Users Table
- id, username, email, password_hash, emp_id, gender, designation, department, role

### Worklog Table
- id, username, date, status, category, task

### Task JSON Structure
```json
{
  "Documentation and Audits": "Task description",
  "Rankings": "Task description",
  "Publications": "Task description",
  "Training and Development": "Task description",
  "Strategic Initiatives": "Task description",
  "Others": "Task description"
}
```

## Features in Detail

### Working Day Calculation
- Sundays (day 0): Non-working
- 3rd Saturday of each month: Non-working
- All other weekdays: Working days
- System prevents entries on non-working days

### AI Summary Analysis
The AI-powered summary feature:
- Analyzes all worklog entries for selected period
- Identifies key activities and trends
- Groups work by category
- Generates professional summary text
- Useful for performance reviews and annual reports

### Date Validation Rules
- **Current date only (after 2nd)**: Can only add current month entries
- **Before/on 2nd of month**: Can add previous month entries
- **7-day edit window**: Can only edit entries from last 7 days
- **No future dates**: Cannot add entries for future dates

## Troubleshooting

### Email Reminders Not Sending
- Check SMTP credentials in `.env`
- Verify Gmail App Password
- Ensure firewall allows port 587
- Check email inbox spam folder

### AI Summaries Not Working
- Verify GEMINI_API_KEY is set in `.env`
- Check API key is valid: https://aistudio.google.com/app/apikey
- Ensure internet connection for API calls
- Check Flask console for error messages

### Database Connection Issues
- Verify PostgreSQL is running
- Check DATABASE_URL format
- Verify database exists and user has permissions
- Test connection: `psql -U username -d iqac_worklog`

### Date Restrictions Blocking Entry
- Remember: No entries on Sundays or 3rd Saturday
- After 2nd of month: Only current month entries allowed
- Check calendar before selecting dates

## Security Notes

- All passwords hashed using Werkzeug security
- Session-based authentication
- CSRF protection on forms
- SQL injection prevention with parameterized queries
- Email credentials stored in `.env` (never in code)
- API keys stored in `.env` (never in code)

## Development

### Project Structure
```
iqac/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (not in git)
├── README.md             # This file
├── SCHEDULER_SETUP.md    # Scheduler configuration guide
├── templates/            # HTML templates
│   ├── login.html
│   ├── dashboard.html
│   ├── admin_report.html
│   ├── admin_report_ai.html
│   ├── user_add_entry.html
│   └── ...
├── static/              # Static files
│   ├── christ_logo.png
│   └── select2.js
└── logo/               # Logo files
```

### Code Style
- PEP 8 compliant Python
- Template variables in lowercase
- Consistent error handling
- SQL queries parameterized to prevent injection

## Future Enhancements

- Dashboard analytics and charts
- Advanced filtering and search
- Bulk entry import/export
- Attendance integration
- Mobile app version
- Multi-language support
- Integration with other university systems

## License

Internal Use Only - CHRIST (Deemed to be University)

## Contributors

- **Concept**: Dr. Cecil Donald
- **Development**: Vaishnavi VK (MCA 2024-26)

## Support

For issues or feature requests, contact the IQAC office or development team.

## Changelog

### Version 1.0.0 (February 2026)
- Initial release
- User registration and authentication
- Worklog entry management
- Report generation
- AI-powered summaries (Gemini API)
- Automated email reminders
- Holiday and leave tracking
- Working day validation
- Print optimization
- Professional formatting
