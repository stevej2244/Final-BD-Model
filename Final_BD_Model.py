# -*- coding: utf-8 -*-
"""
Updated CRM System with Client Name, Address, Mobile fields
Fixed Excel Export and PythonAnywhere ready
"""

from flask import Flask, render_template_string, request, redirect, url_for, session, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import uuid
import os
import pandas as pd
from io import BytesIO
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

app = Flask(__name__)
app.secret_key = "0da277e7aa9e193ef24c8ed5c0a5de16c4c900d998ceb5917d64d5ca6bb4d724"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///crm.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email Configuration - UPDATE THESE WITH YOUR SMTP SETTINGS
EMAIL_CONFIG = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'sender_email': 'naved@maisonsia.com',
    'sender_password': 'brnxvlalwnqozerq',
    'sender_name': 'CRM System'
}

db = SQLAlchemy(app)

# -------------------------------
# MODELS
# -------------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)


class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.String(50), unique=True, nullable=False)
    
    # NEW FIELDS
    client_name = db.Column(db.String(100))
    architect_name = db.Column(db.String(100))
    
    firm_name = db.Column(db.String(100))
    grade = db.Column(db.String(10))
    client_type = db.Column(db.String(10))
    bd_name = db.Column(db.String(50))
    bd_email = db.Column(db.String(100))
    
    # NEW FIELDS
    client_mobile = db.Column(db.String(20))
    address = db.Column(db.String(500))
    
    meeting_date = db.Column(db.Date)
    meeting_time = db.Column(db.Time)
    remark = db.Column(db.String(200))
    assigned_to = db.Column(db.String(50))
    reschedule_date = db.Column(db.Date)
    reschedule_time = db.Column(db.Time)
    reschedule_remark = db.Column(db.String(200))

    # Meeting Status Fields
    not_interested = db.Column(db.Boolean, default=False)
    require_letter = db.Column(db.Boolean, default=False)
    email_catalogue = db.Column(db.Boolean, default=False)
    quotation_sent = db.Column(db.Boolean, default=False)

    # Meeting Status Remarks
    not_interested_remark = db.Column(db.String(500))
    require_letter_remark = db.Column(db.String(500))
    email_catalogue_remark = db.Column(db.String(500))
    quotation_sent_remark = db.Column(db.String(500))

    # Follow-up tracking
    require_letter_followup_date = db.Column(db.Date)
    email_catalogue_followup_date = db.Column(db.Date)
    email_catalogue_second_followup_date = db.Column(db.Date)
    quotation_followup_date = db.Column(db.Date)
    last_followup_update = db.Column(db.String(500))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FollowUpLog(db.Model):
    """Track all follow-up emails sent"""
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.String(50), db.ForeignKey('lead.lead_id'), nullable=False)
    followup_type = db.Column(db.String(50))
    scheduled_date = db.Column(db.Date)
    sent_date = db.Column(db.DateTime)
    status = db.Column(db.String(20))
    email_sent_to = db.Column(db.String(100))
    notes = db.Column(db.String(500))

# -------------------------------
# EMAIL FUNCTIONS
# -------------------------------
def send_email(to_email, subject, body):
    """Send email via SMTP"""
    try:
        msg = MIMEMultipart()
        msg['From'] = f"{EMAIL_CONFIG['sender_name']} <{EMAIL_CONFIG['sender_email']}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'html'))
        
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['sender_password'])
        server.send_message(msg)
        server.quit()
        
        return True, "Email sent successfully"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"


def send_followup_email(lead, followup_type):
    """Send follow-up reminder email to BD"""
    if not lead.bd_email:
        return False, "BD email not available"

    templates = {
        'require_letter': {
            'subject': f'Follow-up Required: {lead.client_name or lead.architect_name or "Lead"} - Letter Request',
            'body': f"""<html><body>
                        <h2>3-Month Follow-up Reminder</h2>
                        <p>Dear {lead.bd_name},</p>
                        <p>This is a reminder for your scheduled follow-up with:</p>
                        <ul>
                            <li><strong>Client:</strong> {lead.client_name or 'N/A'}</li>
                            <li><strong>Architect:</strong> {lead.architect_name or 'N/A'}</li>
                            <li><strong>Firm:</strong> {lead.firm_name or 'N/A'}</li>
                            <li><strong>Lead ID:</strong> {lead.lead_id}</li>
                        </ul>
                        <p>Status: <strong>Letter Required - 3 Month Follow-up</strong></p>
                        <p>Please follow up with this lead regarding the letter request.</p>
                        </body></html>"""
        },
        'email_catalogue_first': {
            'subject': f'Follow-up Call Required: {lead.client_name or lead.architect_name or "Lead"} - Catalogue Sent',
            'body': f"""<html><body>
                        <h2>7-Day Follow-up Reminder</h2>
                        <p>Dear {lead.bd_name},</p>
                        <p>This is your first follow-up reminder for:</p>
                        <ul>
                            <li><strong>Client:</strong> {lead.client_name or 'N/A'}</li>
                            <li><strong>Architect:</strong> {lead.architect_name or 'N/A'}</li>
                            <li><strong>Mobile:</strong> {lead.client_mobile or 'N/A'}</li>
                            <li><strong>Lead ID:</strong> {lead.lead_id}</li>
                        </ul>
                        <p>Status: <strong>Catalogue Sent - First Follow-up</strong></p>
                        <p>Please call to confirm receipt and gather feedback.</p>
                        </body></html>"""
        },
        'email_catalogue_second': {
            'subject': f'FINAL Follow-up: {lead.client_name or lead.architect_name or "Lead"} - Catalogue Interest',
            'body': f"""<html><body>
                        <h2>Final Follow-up Reminder</h2>
                        <p>Dear {lead.bd_name},</p>
                        <p>This is your FINAL follow-up reminder for:</p>
                        <ul>
                            <li><strong>Client:</strong> {lead.client_name or 'N/A'}</li>
                            <li><strong>Architect:</strong> {lead.architect_name or 'N/A'}</li>
                            <li><strong>Lead ID:</strong> {lead.lead_id}</li>
                        </ul>
                        <p>Status: <strong>Catalogue Sent - FINAL Follow-up</strong></p>
                        <p><strong>This is the last automated reminder for this lead.</strong></p>
                        </body></html>"""
        },
        'quotation': {
            'subject': f'15-Day Follow-up: {lead.client_name or lead.architect_name or "Lead"} - Quotation Sent',
            'body': f"""<html><body>
                        <h2>Quotation Follow-up Reminder</h2>
                        <p>Dear {lead.bd_name},</p>
                        <p>This is your 15-day follow-up for:</p>
                        <ul>
                            <li><strong>Client:</strong> {lead.client_name or 'N/A'}</li>
                            <li><strong>Architect:</strong> {lead.architect_name or 'N/A'}</li>
                            <li><strong>Firm:</strong> {lead.firm_name or 'N/A'}</li>
                            <li><strong>Mobile:</strong> {lead.client_mobile or 'N/A'}</li>
                            <li><strong>Lead ID:</strong> {lead.lead_id}</li>
                        </ul>
                        <p>Status: <strong>Quotation Sent - Recurring Follow-up</strong></p>
                        <p>Please follow up on the quotation status.</p>
                        </body></html>"""
        }
    }

    template = templates.get(followup_type)
    if not template:
        return False, "Invalid follow-up type"

    success, message = send_email(lead.bd_email, template['subject'], template['body'])
    log = FollowUpLog(
        lead_id=lead.lead_id,
        followup_type=followup_type,
        scheduled_date=datetime.now().date(),
        sent_date=datetime.now() if success else None,
        status='sent' if success else 'failed',
        email_sent_to=lead.bd_email,
        notes=message
    )
    db.session.add(log)
    db.session.commit()
    return success, message


def check_and_send_followups():
    """Background job to check and send follow-up emails"""
    with app.app_context():
        today = date.today()
        leads = Lead.query.filter(
            (Lead.require_letter_followup_date == today) |
            (Lead.email_catalogue_followup_date == today) |
            (Lead.email_catalogue_second_followup_date == today) |
            (Lead.quotation_followup_date == today)
        ).all()

        for lead in leads:
            if lead.require_letter and lead.require_letter_followup_date == today:
                send_followup_email(lead, 'require_letter')
            if lead.email_catalogue and lead.email_catalogue_followup_date == today:
                send_followup_email(lead, 'email_catalogue_first')
            if lead.email_catalogue and lead.email_catalogue_second_followup_date == today:
                send_followup_email(lead, 'email_catalogue_second')
            if lead.quotation_sent and lead.quotation_followup_date == today:
                send_followup_email(lead, 'quotation')
                lead.quotation_followup_date = today + timedelta(days=15)
        db.session.commit()

scheduler = BackgroundScheduler()
scheduler.add_job(func=check_and_send_followups, trigger=CronTrigger(hour=9, minute=0))
scheduler.start()

# -------------------------------
# HELPER FUNCTIONS
# -------------------------------

def login_required(f):
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def admin_required(f):
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            flash("Access denied. Admin privileges required.")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# -------------------------------
# SAFE DB INIT & DEFAULT ADMIN
# -------------------------------
def init_db():
    with app.app_context():
        db.create_all()
        
        admin = User.query.filter_by(username="admin").first()
        if not admin:
            admin = User(username="admin", role="admin")
            admin.set_password("admin")
            db.session.add(admin)
            db.session.commit()
            print("Created new admin user")
        elif not admin.password_hash:
            admin.set_password("admin")
            db.session.commit()
            print("Fixed admin user password")
        else:
            print("Admin user already exists with valid password")

init_db()

# -------------------------------
# BASE TEMPLATE FUNCTION
# -------------------------------
def render_page(content, title="CRM"):
    username = session.get('username', 'User')
    role = session.get('role', 'Unknown')
    
    base_template = f"""
<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: Arial, sans-serif; margin:0; padding:0; background-color: #f4f4f4; }}
        .sidebar {{ width:220px; background:#2c3e50; height:100vh; position:fixed; color:white; overflow-y: auto; }}
        .sidebar h2 {{ text-align:center; padding: 20px 10px; margin: 0; background: #34495e; }}
        .sidebar a {{ 
            color:white; display:block; padding:12px 15px; text-decoration:none; 
            border-bottom: 1px solid #34495e; transition: background 0.3s;
        }}
        .sidebar a:hover {{ background:#34495e; }}
        .content {{ margin-left:230px; padding:20px; min-height: 100vh; }}
        .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .form-group {{ margin-bottom:15px; }}
        label {{ display:block; margin-bottom:5px; font-weight: bold; color: #2c3e50; }}
        input, select, textarea {{ 
            width:100%; padding:10px; border: 1px solid #ddd; border-radius: 4px; 
            font-size: 14px; transition: border-color 0.3s;
        }}
        input:focus, select:focus, textarea:focus {{ 
            outline: none; border-color: #3498db; box-shadow: 0 0 5px rgba(52, 152, 219, 0.3);
        }}
        button {{ 
            background:#3498db; color:white; padding:10px 20px; border:none; border-radius:4px; 
            cursor:pointer; font-size: 14px; transition: background 0.3s;
        }}
        button:hover {{ background:#2980b9; }}
        .flash {{ 
            padding: 10px; margin: 10px 0; border-radius: 4px; 
            background: #e74c3c; color: white; 
        }}
        .flash.success {{ background: #27ae60; }}
        table {{ 
            width: 100%; border-collapse: collapse; background: white; 
            border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #34495e; color: white; font-weight: bold; }}
        tr:hover {{ background: #f8f9fa; }}
        .user-info {{ 
            position: absolute; top: 10px; right: 20px; color: #7f8c8d; 
            font-size: 14px; 
        }}
        .status-badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
        }}
        .status-not-interested {{ background: #e74c3c; color: white; }}
        .status-require-letter {{ background: #f39c12; color: white; }}
        .status-email-catalogue {{ background: #3498db; color: white; }}
        .status-quotation {{ background: #27ae60; color: white; }}
        @media (max-width: 768px) {{
            .sidebar {{ width: 100%; height: auto; position: relative; }}
            .content {{ margin-left: 0; }}
        }}
    </style>
</head>
<body>
<div class="sidebar">
    <h2>CRM System</h2>
    <a href="{url_for('dashboard')}">📊 Dashboard</a>
    <a href="{url_for('meeting_dashboard')}">📋 Meeting Dashboard</a>
    <a href="{url_for('new_lead')}">➕ New Lead</a>
    <a href="{url_for('assign_lead')}">📋 Assign Lead</a>
    <a href="{url_for('reschedule_meeting')}">📅 Reschedule Meeting</a>
    <a href="{url_for('meeting_stats')}">📈 Meeting Stats</a>
    <a href="{url_for('export_data')}">📤 Export Data</a>
    <a href="{url_for('manage_users')}">👥 Manage Users</a>
    <a href="{url_for('email_settings')}">✉️ Email Settings</a>
    <a href="{url_for('logout')}">🚪 Logout</a>
</div>
<div class="content">
    <div class="user-info">
        Welcome, {username} ({role})
    </div>
    {{{{ flash_messages }}}}
    {content}
</div>
</body>
</html>
"""
    
    flash_html = ""
    flashed_messages = session.get('_flashes', [])
    if flashed_messages:
        for category, msg in flashed_messages:
            flash_class = 'success' if category == 'success' else ''
            flash_html += f'<div class="flash {flash_class}">{msg}</div>'
        session.pop('_flashes', None)
    
    return base_template.replace('{{ flash_messages }}', flash_html)

# -------------------------------
# LOGIN / LOGOUT
# -------------------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        if not username or not password:
            flash("Please enter both username and password")
        else:
            user = User.query.filter_by(username=username).first()
            if user:
                if not user.password_hash:
                    flash("User account needs to be reset. Contact administrator.")
                elif user.check_password(password):
                    session["user_id"] = user.id
                    session["username"] = user.username
                    session["role"] = user.role
                    flash("Login successful!", "success")
                    return redirect(url_for("dashboard"))
                else:
                    flash("Invalid username or password")
            else:
                flash("Invalid username or password")
    
    content = """
    <div class="card" style="max-width: 400px; margin: 100px auto;">
        <h2 style="text-align: center; color: #2c3e50; margin-bottom: 30px;">Login to CRM</h2>
        <form method="post">
            <div class="form-group">
                <label for="username">Username:</label>
                <input type="text" id="username" name="username" required>
            </div>
            <div class="form-group">
                <label for="password">Password:</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit" style="width: 100%;">Login</button>
        </form>
        <div style="margin-top: 20px; text-align: center; color: #7f8c8d; font-size: 12px;">
            Default: admin / admin
        </div>
    </div>
    """
    return render_page(content, "Login - CRM")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully!", "success")
    return redirect(url_for("login"))

# -------------------------------
# DASHBOARD
# -------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    leads = Lead.query.order_by(Lead.updated_at.desc()).limit(50).all()
    total_leads = Lead.query.count()
    assigned_leads = Lead.query.filter(Lead.assigned_to.isnot(None)).count()
    pending_leads = Lead.query.filter_by(assigned_to=None).count()
    
    today = date.today()
    pending_followups = Lead.query.filter(
        (Lead.require_letter_followup_date <= today) |
        (Lead.email_catalogue_followup_date <= today) |
        (Lead.email_catalogue_second_followup_date <= today) |
        (Lead.quotation_followup_date <= today)
    ).count()
    
    content = f"""
    <div class="card">
        <h2>Dashboard Overview</h2>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0;">
            <div style="background: #3498db; color: white; padding: 20px; border-radius: 8px; text-align: center;">
                <h3 style="margin: 0;">{total_leads}</h3>
                <p style="margin: 5px 0 0 0;">Total Leads</p>
            </div>
            <div style="background: #27ae60; color: white; padding: 20px; border-radius: 8px; text-align: center;">
                <h3 style="margin: 0;">{assigned_leads}</h3>
                <p style="margin: 5px 0 0 0;">Assigned Leads</p>
            </div>
            <div style="background: #e74c3c; color: white; padding: 20px; border-radius: 8px; text-align: center;">
                <h3 style="margin: 0;">{pending_leads}</h3>
                <p style="margin: 5px 0 0 0;">Pending Assignment</p>
            </div>
            <div style="background: #f39c12; color: white; padding: 20px; border-radius: 8px; text-align: center;">
                <h3 style="margin: 0;">{pending_followups}</h3>
                <p style="margin: 5px 0 0 0;">Pending Follow-ups</p>
            </div>
        </div>
    </div>
    
    <div class="card">
        <h3>Recent Leads</h3>
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr>
                        <th>Lead ID</th>
                        <th>Client Name</th>
                        <th>Architect</th>
                        <th>Firm</th>
                        <th>Grade</th>
                        <th>BD Name</th>
                        <th>Meeting Date</th>
                        <th>Assigned To</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    for lead in leads:
        status = "Assigned" if lead.assigned_to else "Pending"
        meeting_date_str = lead.meeting_date.strftime("%Y-%m-%d") if lead.meeting_date else "N/A"
        content += f"""
                    <tr>
                        <td>{lead.lead_id}</td>
                        <td>{lead.client_name or 'N/A'}</td>
                        <td>{lead.architect_name or 'N/A'}</td>
                        <td>{lead.firm_name or 'N/A'}</td>
                        <td>{lead.grade or 'N/A'}</td>
                        <td>{lead.bd_name or 'N/A'}</td>
                        <td>{meeting_date_str}</td>
                        <td>{lead.assigned_to or 'Not Assigned'}</td>
                        <td>{status}</td>
                    </tr>
        """
    
    content += """
                </tbody>
            </table>
        </div>
    </div>
    """
    
    return render_page(content, "Dashboard - CRM")

# -------------------------------
# MEETING DASHBOARD WITH FILTERS
# -------------------------------
@app.route("/meeting_dashboard", methods=["GET", "POST"])
@login_required
def meeting_dashboard():
    bd_names = db.session.query(Lead.bd_name).distinct().filter(Lead.bd_name.isnot(None)).all()
    bd_names = [name[0] for name in bd_names if name[0]]
    
    query = Lead.query
    
    filter_bd = request.args.get('filter_bd', '')
    filter_status = request.args.get('filter_status', '')
    
    if filter_bd:
        query = query.filter(Lead.bd_name == filter_bd)
    
    if filter_status:
        if filter_status == 'not_interested':
            query = query.filter(Lead.not_interested == True)
        elif filter_status == 'require_letter':
            query = query.filter(Lead.require_letter == True)
        elif filter_status == 'email_catalogue':
            query = query.filter(Lead.email_catalogue == True)
        elif filter_status == 'quotation_sent':
            query = query.filter(Lead.quotation_sent == True)
    
    leads = query.order_by(Lead.updated_at.desc()).all()
    
    content = f"""
    <div class="card">
        <h2>Meeting Status Dashboard</h2>
        
        <form method="get" style="margin: 20px 0;">
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px;">
                <div class="form-group">
                    <label for="filter_bd">Filter by BD Name:</label>
                    <select id="filter_bd" name="filter_bd" onchange="this.form.submit()">
                        <option value="">All BDs</option>
    """
    
    for bd in bd_names:
        selected = 'selected' if bd == filter_bd else ''
        content += f'<option value="{bd}" {selected}>{bd}</option>'
    
    content += f"""
                    </select>
                </div>
                <div class="form-group">
                    <label for="filter_status">Filter by Meeting Status:</label>
                    <select id="filter_status" name="filter_status" onchange="this.form.submit()">
                        <option value="">All Statuses</option>
                        <option value="not_interested" {'selected' if filter_status == 'not_interested' else ''}>Not Interested</option>
                        <option value="email_catalogue" {'selected' if filter_status == 'email_catalogue' else ''}>Email Catalogue</option>
                        <option value="require_letter" {'selected' if filter_status == 'require_letter' else ''}>Require Letter</option>
                        <option value="quotation_sent" {'selected' if filter_status == 'quotation_sent' else ''}>Quotation Sent</option>
                    </select>
                </div>
                <div class="form-group" style="display: flex; align-items: flex-end;">
                    <button type="submit" style="margin-right: 10px;">Apply Filters</button>
                    <a href="{url_for('meeting_dashboard')}" style="padding: 10px 20px; background: #95a5a6; color: white; text-decoration: none; border-radius: 4px;">Clear</a>
                </div>
            </div>
        </form>
        
        <div style="margin: 20px 0;">
            <strong>Total Results:</strong> {len(leads)} leads
        </div>
        
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr>
                        <th>Lead ID</th>
                        <th>Client/Architect</th>
                        <th>BD Name</th>
                        <th>Meeting Status</th>
                        <th>Remarks</th>
                        <th>Follow-up Date</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    for lead in leads:
        status_badges = []
        remarks = []
        followup_date = "N/A"
        
        if lead.not_interested:
            status_badges.append('<span class="status-badge status-not-interested">Not Interested</span>')
            if lead.not_interested_remark:
                remarks.append(f"Not Interested: {lead.not_interested_remark[:50]}...")
        if lead.require_letter:
            status_badges.append('<span class="status-badge status-require-letter">Require Letter</span>')
            if lead.require_letter_remark:
                remarks.append(f"Require Letter: {lead.require_letter_remark[:50]}...")
            if lead.require_letter_followup_date:
                followup_date = lead.require_letter_followup_date.strftime("%Y-%m-%d")
        if lead.email_catalogue:
            status_badges.append('<span class="status-badge status-email-catalogue">Email Catalogue</span>')
            if lead.email_catalogue_remark:
                remarks.append(f"Email Catalogue: {lead.email_catalogue_remark[:50]}...")
            if lead.email_catalogue_followup_date:
                followup_date = lead.email_catalogue_followup_date.strftime("%Y-%m-%d")
        if lead.quotation_sent:
            status_badges.append('<span class="status-badge status-quotation">Quotation Sent</span>')
            if lead.quotation_sent_remark:
                remarks.append(f"Quotation: {lead.quotation_sent_remark[:50]}...")
            if lead.quotation_followup_date:
                followup_date = lead.quotation_followup_date.strftime("%Y-%m-%d")
        
        status_display = ' '.join(status_badges) if status_badges else '<span style="color: #95a5a6;">No Status</span>'
        remarks_display = '<br>'.join(remarks) if remarks else "N/A"
        client_arch_display = f"{lead.client_name or ''} / {lead.architect_name or 'N/A'}"
        
        content += f"""
                    <tr>
                        <td>{lead.lead_id}</td>
                        <td>{client_arch_display}</td>
                        <td>{lead.bd_name or 'N/A'}</td>
                        <td>{status_display}</td>
                        <td style="font-size: 12px;">{remarks_display}</td>
                        <td>{followup_date}</td>
                        <td>
                            <a href="{url_for('update_meeting_status', lead_id=lead.lead_id)}" style="color: #3498db; text-decoration: none;">Update</a>
                        </td>
                    </tr>
        """
    
    content += """
                </tbody>
            </table>
        </div>
    </div>
    """
    
    return render_page(content, "Meeting Dashboard - CRM")

# -------------------------------
# UPDATE MEETING STATUS
# -------------------------------
@app.route("/update_meeting_status/<lead_id>", methods=["GET", "POST"])
@login_required
def update_meeting_status(lead_id):
    lead = Lead.query.filter_by(lead_id=lead_id).first()
    if not lead:
        flash("Lead not found")
        return redirect(url_for("meeting_dashboard"))
    
    if request.method == "POST":
        try:
            was_require_letter = lead.require_letter
            was_email_catalogue = lead.email_catalogue
            was_quotation = lead.quotation_sent
            
            lead.not_interested = "not_interested" in request.form
            lead.require_letter = "require_letter" in request.form
            lead.email_catalogue = "email_catalogue" in request.form
            lead.quotation_sent = "quotation_sent" in request.form
            
            # Update remarks for each status
            if lead.not_interested:
                lead.not_interested_remark = request.form.get("not_interested_remark", "").strip()
            if lead.require_letter:
                lead.require_letter_remark = request.form.get("require_letter_remark", "").strip()
            if lead.email_catalogue:
                lead.email_catalogue_remark = request.form.get("email_catalogue_remark", "").strip()
            if lead.quotation_sent:
                lead.quotation_sent_remark = request.form.get("quotation_sent_remark", "").strip()
            
            update_note = request.form.get("update_note", "").strip()
            if update_note:
                lead.last_followup_update = f"{datetime.now().strftime('%Y-%m-%d %H:%M')}: {update_note}"
            
            # Handle Require Letter - 3 months follow-up
            if lead.require_letter and not was_require_letter:
                lead.require_letter_followup_date = date.today() + timedelta(days=90)
                if lead.bd_email:
                    send_followup_email(lead, 'require_letter')
                    flash("Require Letter status set. BD will receive follow-up email in 3 months.", "success")
            
            # Handle Email Catalogue - 7 days first follow-up
            if lead.email_catalogue and not was_email_catalogue:
                lead.email_catalogue_followup_date = date.today() + timedelta(days=7)
                lead.email_catalogue_second_followup_date = date.today() + timedelta(days=14)
                if lead.bd_email:
                    flash("Email Catalogue status set. BD will receive follow-up email in 7 days.", "success")
            
            # Handle Quotation Sent - 15 days follow-up
            if lead.quotation_sent and not was_quotation:
                lead.quotation_followup_date = date.today() + timedelta(days=15)
                if lead.bd_email:
                    flash("Quotation status set. BD will receive follow-up email in 15 days.", "success")
            
            db.session.commit()
            flash(f"Meeting status for lead {lead_id} updated successfully!", "success")
            return redirect(url_for("meeting_dashboard"))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating meeting status: {str(e)}")
    
    content = f"""
    <div class="card">
        <h2>Update Meeting Status - {lead.lead_id}</h2>
        
        <div style="background: #ecf0f1; padding: 15px; border-radius: 5px; margin-bottom: 20px;">
            <h3 style="margin: 0 0 10px 0;">Lead Information</h3>
            <p><strong>Client Name:</strong> {lead.client_name or 'N/A'}</p>
            <p><strong>Architect:</strong> {lead.architect_name or 'N/A'}</p>
            <p><strong>Firm:</strong> {lead.firm_name or 'N/A'}</p>
            <p><strong>Mobile:</strong> {lead.client_mobile or 'N/A'}</p>
            <p><strong>BD Name:</strong> {lead.bd_name or 'N/A'}</p>
            <p><strong>BD Email:</strong> {lead.bd_email or 'Not provided'}</p>
            <p><strong>Meeting Date:</strong> {lead.meeting_date.strftime("%Y-%m-%d") if lead.meeting_date else 'N/A'}</p>
        </div>
        
        <form method="post">
            <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #ffc107;">
                <h4 style="margin: 0 0 15px 0;">Meeting Status Options</h4>
                
                <!-- Not Interested -->
                <div style="border: 2px solid #e74c3c; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                    <label style="display: flex; align-items: center;">
                        <input type="checkbox" name="not_interested" {"checked" if lead.not_interested else ""} 
                               style="width: auto; margin-right: 10px;" id="not_interested_check"
                               onchange="toggleRemark('not_interested')">
                        <strong style="color: #e74c3c;">Not Interested</strong>
                    </label>
                    <p style="margin: 5px 0; font-size: 12px; color: #7f8c8d;">No follow-up required</p>
                    <div id="not_interested_remark" style="display: {'block' if lead.not_interested else 'none'}; margin-top: 10px;">
                        <label for="not_interested_remark_text">Remark:</label>
                        <textarea id="not_interested_remark_text" name="not_interested_remark" rows="2" 
                                  placeholder="Why not interested?">{lead.not_interested_remark or ''}</textarea>
                    </div>
                </div>
                
                <!-- Require Letter -->
                <div style="border: 2px solid #f39c12; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                    <label style="display: flex; align-items: center;">
                        <input type="checkbox" name="require_letter" {"checked" if lead.require_letter else ""} 
                               style="width: auto; margin-right: 10px;" id="require_letter_check"
                               onchange="toggleRemark('require_letter')">
                        <strong style="color: #f39c12;">Require Letter</strong>
                    </label>
                    <p style="margin: 5px 0; font-size: 12px; color: #7f8c8d;">Follow-up meeting after 3 months</p>
                    {f'<p style="margin: 5px 0; font-size: 11px; color: #27ae60;">Next follow-up: {lead.require_letter_followup_date.strftime("%Y-%m-%d")}</p>' if lead.require_letter_followup_date else ''}
                    <div id="require_letter_remark" style="display: {'block' if lead.require_letter else 'none'}; margin-top: 10px;">
                        <label for="require_letter_remark_text">Remark:</label>
                        <textarea id="require_letter_remark_text" name="require_letter_remark" rows="2" 
                                  placeholder="Letter details, expectations...">{lead.require_letter_remark or ''}</textarea>
                    </div>
                </div>
                
                <!-- Email Catalogue -->
                <div style="border: 2px solid #3498db; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                    <label style="display: flex; align-items: center;">
                        <input type="checkbox" name="email_catalogue" {"checked" if lead.email_catalogue else ""} 
                               style="width: auto; margin-right: 10px;" id="email_catalogue_check"
                               onchange="toggleRemark('email_catalogue')">
                        <strong style="color: #3498db;">Email Catalogue</strong>
                    </label>
                    <p style="margin: 5px 0; font-size: 12px; color: #7f8c8d;">Follow-up call after 7 days (max 2 follow-ups)</p>
                    {f'<p style="margin: 5px 0; font-size: 11px; color: #27ae60;">1st follow-up: {lead.email_catalogue_followup_date.strftime("%Y-%m-%d")}</p>' if lead.email_catalogue_followup_date else ''}
                    {f'<p style="margin: 5px 0; font-size: 11px; color: #e74c3c;">2nd follow-up: {lead.email_catalogue_second_followup_date.strftime("%Y-%m-%d")} (FINAL)</p>' if lead.email_catalogue_second_followup_date else ''}
                    <div id="email_catalogue_remark" style="display: {'block' if lead.email_catalogue else 'none'}; margin-top: 10px;">
                        <label for="email_catalogue_remark_text">Remark:</label>
                        <textarea id="email_catalogue_remark_text" name="email_catalogue_remark" rows="2" 
                                  placeholder="Catalogue sent details, response...">{lead.email_catalogue_remark or ''}</textarea>
                    </div>
                </div>
                
                <!-- Quotation Sent -->
                <div style="border: 2px solid #27ae60; padding: 15px; border-radius: 5px; margin-bottom: 15px;">
                    <label style="display: flex; align-items: center;">
                        <input type="checkbox" name="quotation_sent" {"checked" if lead.quotation_sent else ""} 
                               style="width: auto; margin-right: 10px;" id="quotation_sent_check"
                               onchange="toggleRemark('quotation_sent')">
                        <strong style="color: #27ae60;">Quotation Sent</strong>
                    </label>
                    <p style="margin: 5px 0; font-size: 12px; color: #7f8c8d;">Follow-up every 15 days (recurring)</p>
                    {f'<p style="margin: 5px 0; font-size: 11px; color: #27ae60;">Next follow-up: {lead.quotation_followup_date.strftime("%Y-%m-%d")}</p>' if lead.quotation_followup_date else ''}
                    <div id="quotation_sent_remark" style="display: {'block' if lead.quotation_sent else 'none'}; margin-top: 10px;">
                        <label for="quotation_sent_remark_text">Remark:</label>
                        <textarea id="quotation_sent_remark_text" name="quotation_sent_remark" rows="2" 
                                  placeholder="Quotation details, amount, feedback...">{lead.quotation_sent_remark or ''}</textarea>
                    </div>
                </div>
            </div>
            
            <div class="form-group">
                <label for="update_note">General Update Note:</label>
                <textarea id="update_note" name="update_note" rows="3" 
                          placeholder="Add any general notes about this meeting status update...">{lead.last_followup_update or ''}</textarea>
            </div>
            
            <div style="display: flex; gap: 10px;">
                <button type="submit">Update Status</button>
                <a href="{url_for('meeting_dashboard')}" style="padding: 10px 20px; background: #95a5a6; color: white; text-decoration: none; border-radius: 4px; display: inline-block;">Cancel</a>
            </div>
        </form>
        
        {f'''
        <div style="margin-top: 30px; padding: 15px; background: #e8f5e9; border-radius: 5px; border-left: 4px solid #27ae60;">
            <h4 style="margin: 0 0 10px 0;">✅ Email Notifications Enabled</h4>
            <p style="margin: 0; font-size: 14px;">BD will receive automated follow-up emails at: <strong>{lead.bd_email}</strong></p>
        </div>
        ''' if lead.bd_email else '''
        <div style="margin-top: 30px; padding: 15px; background: #ffebee; border-radius: 5px; border-left: 4px solid #e74c3c;">
            <h4 style="margin: 0 0 10px 0;">⚠️ No Email Configured</h4>
            <p style="margin: 0; font-size: 14px;">Add BD email in "New Lead" to enable automated follow-up emails.</p>
        </div>
        '''}
    </div>
    
    <script>
        function toggleRemark(statusType) {{
            const checkbox = document.getElementById(statusType + '_check');
            const remarkDiv = document.getElementById(statusType + '_remark');
            remarkDiv.style.display = checkbox.checked ? 'block' : 'none';
        }}
    </script>
    """
    
    return render_page(content, f"Update Meeting Status - {lead_id}")

# -------------------------------
# NEW LEAD
# -------------------------------
@app.route("/new_lead", methods=["GET", "POST"])
@login_required
def new_lead():
    if request.method == "POST":
        try:
            meeting_date = request.form.get("meeting_date")
            meeting_time = request.form.get("meeting_time")
            
            meeting_date_obj = datetime.strptime(meeting_date, "%Y-%m-%d").date() if meeting_date else None
            meeting_time_obj = datetime.strptime(meeting_time, "%H:%M").time() if meeting_time else None
            
            lead = Lead(
                lead_id=str(uuid.uuid4())[:8].upper(),
                client_name=request.form.get("client_name", "").strip(),
                architect_name=request.form.get("architect_name", "").strip(),
                firm_name=request.form.get("firm_name", "").strip(),
                grade=request.form.get("grade"),
                client_type=request.form.get("client_type"),
                bd_name=request.form.get("bd_name", "").strip(),
                bd_email=request.form.get("bd_email", "").strip(),
                client_mobile=request.form.get("client_mobile", "").strip(),
                address=request.form.get("address", "").strip(),
                meeting_date=meeting_date_obj,
                meeting_time=meeting_time_obj,
                remark=request.form.get("remark", "").strip()
            )
            db.session.add(lead)
            db.session.commit()
            flash(f"Lead {lead.lead_id} added successfully!", "success")
            return redirect(url_for("new_lead"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding lead: {str(e)}")
    
    content = """
    <div class="card">
        <h2>Add New Lead</h2>
        <form method="post">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div class="form-group">
                    <label for="client_name">Client Name:</label>
                    <input type="text" id="client_name" name="client_name" placeholder="Enter client name">
                </div>
                <div class="form-group">
                    <label for="architect_name">Architect Name:</label>
                    <input type="text" id="architect_name" name="architect_name" placeholder="Enter architect name">
                </div>
                <div class="form-group">
                    <label for="firm_name">Firm Name:</label>
                    <input type="text" id="firm_name" name="firm_name" placeholder="Enter firm name">
                </div>
                <div class="form-group">
                    <label for="grade">Grade:</label>
                    <select id="grade" name="grade">
                        <option value="">Select Grade</option>
                        <option value="A+">A+</option>
                        <option value="A">A</option>
                        <option value="B">B</option>
                        <option value="C">C</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="client_type">Client Type:</label>
                    <select id="client_type" name="client_type">
                        <option value="">Select Type</option>
                        <option value="CRR">CRR</option>
                        <option value="NBD">NBD</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="bd_name">BD Name *:</label>
                    <input type="text" id="bd_name" name="bd_name" required placeholder="Enter BD name">
                </div>
                <div class="form-group">
                    <label for="bd_email">BD Email (for follow-up notifications) *:</label>
                    <input type="email" id="bd_email" name="bd_email" placeholder="bd@example.com" required>
                </div>
                <div class="form-group">
                    <label for="client_mobile">Client Mobile Number:</label>
                    <input type="tel" id="client_mobile" name="client_mobile" placeholder="+91 1234567890">
                </div>
                <div class="form-group">
                    <label for="meeting_date">Meeting Date:</label>
                    <input type="date" id="meeting_date" name="meeting_date">
                </div>
                <div class="form-group">
                    <label for="meeting_time">Meeting Time:</label>
                    <input type="time" id="meeting_time" name="meeting_time">
                </div>
            </div>
            
            <div class="form-group">
                <label for="address">Address:</label>
                <textarea id="address" name="address" rows="3" placeholder="Enter full address..."></textarea>
            </div>
            
            <div class="form-group">
                <label for="remark">Remark:</label>
                <textarea id="remark" name="remark" rows="4" placeholder="Any additional remarks..."></textarea>
            </div>
            
            <div style="background: #e3f2fd; padding: 15px; border-radius: 5px; margin: 15px 0; border-left: 4px solid #2196f3;">
                <strong>📧 Note:</strong> BD Email is required for automated follow-up reminders. The system will send emails for:
                <ul style="margin: 10px 0 0 20px;">
                    <li><strong>Require Letter:</strong> 3 months follow-up</li>
                    <li><strong>Email Catalogue:</strong> 7 days (1st) + 7 days (2nd final)</li>
                    <li><strong>Quotation Sent:</strong> Every 15 days (recurring)</li>
                </ul>
            </div>
            <button type="submit">Add Lead</button>
        </form>
    </div>
    """
    
    return render_page(content, "New Lead - CRM")

# -------------------------------
# ASSIGN LEAD
# -------------------------------
@app.route("/assign_lead", methods=["GET", "POST"])
@login_required
def assign_lead():
    leads = Lead.query.filter_by(assigned_to=None).all()
    
    if request.method == "POST":
        try:
            lead_id = request.form.get("lead_id")
            assigned_to = request.form.get("assigned_to", "").strip()
            
            if not assigned_to:
                flash("Please enter the name to assign the lead to")
            else:
                lead = Lead.query.filter_by(lead_id=lead_id).first()
                if lead:
                    lead.assigned_to = assigned_to
                    db.session.commit()
                    flash(f"Lead {lead_id} assigned to {assigned_to} successfully!", "success")
                else:
                    flash("Lead not found")
                return redirect(url_for("assign_lead"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error assigning lead: {str(e)}")
    
    content = f"""
    <div class="card">
        <h2>Assign Lead</h2>
        {f'<p><strong>Unassigned Leads:</strong> {len(leads)}</p>' if leads else '<p>No unassigned leads available.</p>'}
        
        {'<form method="post">' if leads else ''}
    """
    
    if leads:
        content += """
            <div class="form-group">
                <label for="lead_id">Select Lead:</label>
                <select id="lead_id" name="lead_id" required>
        """
        for lead in leads:
            display_name = lead.client_name or lead.architect_name or "Unknown"
            content += f'<option value="{lead.lead_id}">{lead.lead_id} - {display_name} ({lead.firm_name or "No Firm"})</option>'
        
        content += """
                </select>
            </div>
            <div class="form-group">
                <label for="assigned_to">Assign To *:</label>
                <input type="text" id="assigned_to" name="assigned_to" required placeholder="Enter name">
            </div>
            <button type="submit">Assign Lead</button>
        </form>
        """
    
    content += "</div>"
    
    return render_page(content, "Assign Lead - CRM")

# -------------------------------
# RESCHEDULE MEETING
# -------------------------------
@app.route("/reschedule_meeting", methods=["GET", "POST"])
@login_required
def reschedule_meeting():
    leads = Lead.query.all()
    
    if request.method == "POST":
        try:
            lead_id = request.form.get("lead_id")
            lead = Lead.query.filter_by(lead_id=lead_id).first()
            
            if lead:
                reschedule_date = request.form.get("reschedule_date")
                reschedule_time = request.form.get("reschedule_time")
                
                reschedule_date_obj = datetime.strptime(reschedule_date, "%Y-%m-%d").date() if reschedule_date else None
                reschedule_time_obj = datetime.strptime(reschedule_time, "%H:%M").time() if reschedule_time else None
                
                lead.reschedule_date = reschedule_date_obj
                lead.reschedule_time = reschedule_time_obj
                lead.reschedule_remark = request.form.get("remark", "").strip()
                db.session.commit()
                flash(f"Meeting for lead {lead_id} rescheduled successfully!", "success")
            else:
                flash("Lead not found")
            return redirect(url_for("reschedule_meeting"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error rescheduling meeting: {str(e)}")
    
    content = """
    <div class="card">
        <h2>Reschedule Meeting</h2>
        <form method="post">
            <div class="form-group">
                <label for="lead_id">Select Lead:</label>
                <select id="lead_id" name="lead_id" required>
    """
    
    for lead in leads:
        display_name = lead.client_name or lead.architect_name or "Unknown"
        content += f'<option value="{lead.lead_id}">{lead.lead_id} - {display_name}</option>'
    
    content += """
                </select>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div class="form-group">
                    <label for="reschedule_date">New Meeting Date:</label>
                    <input type="date" id="reschedule_date" name="reschedule_date">
                </div>
                <div class="form-group">
                    <label for="reschedule_time">New Meeting Time:</label>
                    <input type="time" id="reschedule_time" name="reschedule_time">
                </div>
            </div>
            <div class="form-group">
                <label for="remark">Remark:</label>
                <textarea id="remark" name="remark" rows="4" placeholder="Reason for rescheduling..."></textarea>
            </div>
            <button type="submit">Reschedule Meeting</button>
        </form>
    </div>
    """
    
    return render_page(content, "Reschedule Meeting - CRM")

# -------------------------------
# MEETING STATS
# -------------------------------
@app.route("/meeting_stats", methods=["GET"])
@login_required
def meeting_stats():
    flash("Please use the new 'Meeting Dashboard' for updating meeting statuses with follow-up tracking.", "success")
    return redirect(url_for("meeting_dashboard"))

# -------------------------------
# EMAIL SETTINGS
# -------------------------------
@app.route("/email_settings", methods=["GET", "POST"])
@login_required
@admin_required
def email_settings():
    if request.method == "POST":
        flash("Email settings updated! (Note: Restart app to apply changes)", "success")
        return redirect(url_for("email_settings"))
    
    content = f"""
    <div class="card">
        <h2>Email Configuration</h2>
        
        <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid #ffc107;">
            <h4 style="margin: 0 0 10px 0;">⚠️ Configuration Required</h4>
            <p style="margin: 0;">To enable automated follow-up emails, update the EMAIL_CONFIG dictionary in the code (lines 18-24):</p>
        </div>
        
        <div style="background: #263238; color: #aed581; padding: 20px; border-radius: 5px; font-family: monospace; margin: 20px 0; overflow-x: auto;">
EMAIL_CONFIG = {{<br>
&nbsp;&nbsp;&nbsp;&nbsp;'smtp_server': 'smtp.gmail.com',<br>
&nbsp;&nbsp;&nbsp;&nbsp;'smtp_port': 587,<br>
&nbsp;&nbsp;&nbsp;&nbsp;'sender_email': '<span style="color: #ffab00;">your-email@gmail.com</span>',<br>
&nbsp;&nbsp;&nbsp;&nbsp;'sender_password': '<span style="color: #ffab00;">your-app-password</span>',<br>
&nbsp;&nbsp;&nbsp;&nbsp;'sender_name': 'CRM System'<br>
}}
        </div>
        
        <div class="card" style="background: #f5f5f5;">
            <h3>Current Settings</h3>
            <table>
                <tr><td><strong>SMTP Server:</strong></td><td>{EMAIL_CONFIG['smtp_server']}</td></tr>
                <tr><td><strong>SMTP Port:</strong></td><td>{EMAIL_CONFIG['smtp_port']}</td></tr>
                <tr><td><strong>Sender Email:</strong></td><td>{EMAIL_CONFIG['sender_email']}</td></tr>
                <tr><td><strong>Sender Name:</strong></td><td>{EMAIL_CONFIG['sender_name']}</td></tr>
                <tr>
                    <td><strong>Password:</strong></td>
                    <td>{'✅ Configured' if EMAIL_CONFIG['sender_password'] != 'your-app-password' else '⚠️ Not Configured'}</td>
                </tr>
            </table>
        </div>
        
        <div style="background: #e3f2fd; padding: 15px; border-radius: 5px; margin-top: 20px; border-left: 4px solid #2196f3;">
            <h4 style="margin: 0 0 10px 0;">📧 Gmail Setup Instructions</h4>
            <ol style="margin: 0; padding-left: 20px;">
                <li>Go to your Google Account settings</li>
                <li>Enable 2-Step Verification</li>
                <li>Go to Security → App Passwords</li>
                <li>Generate an app password for "Mail"</li>
                <li>Use that password in the configuration above</li>
            </ol>
        </div>
        
        <div style="background: #f3e5f5; padding: 15px; border-radius: 5px; margin-top: 20px; border-left: 4px solid #9c27b0;">
            <h4 style="margin: 0 0 10px 0;">🔄 Follow-up Schedule</h4>
            <p style="margin: 0;"><strong>Automated emails run daily at 9:00 AM</strong></p>
            <ul style="margin: 10px 0 0 20px;">
                <li><strong>Require Letter:</strong> 3 months (90 days)</li>
                <li><strong>Email Catalogue (1st):</strong> 7 days after status set</li>
                <li><strong>Email Catalogue (2nd):</strong> 14 days after status set (FINAL)</li>
                <li><strong>Quotation Sent:</strong> Every 15 days (recurring)</li>
            </ul>
        </div>
    </div>
    """
    
    return render_page(content, "Email Settings - CRM")

# -------------------------------
# EXPORT DATA
# -------------------------------
@app.route("/export_data", methods=["GET", "POST"])
@login_required
def export_data():
    if request.method == "POST":
        try:
            export_type = request.form.get("export_type", "all")
            start_date = request.form.get("start_date")
            end_date = request.form.get("end_date")
            
            query = Lead.query
            
            if export_type == "date_range" and start_date and end_date:
                start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
                end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
                query = query.filter(Lead.meeting_date.between(start_date_obj, end_date_obj))
            elif export_type == "created_range" and start_date and end_date:
                start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
                end_datetime = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                query = query.filter(Lead.created_at.between(start_datetime, end_datetime))
            
            leads = query.order_by(Lead.created_at.desc()).all()
            
            if not leads:
                flash("No data found for the selected criteria")
                return redirect(url_for("export_data"))
            
            output = BytesIO()
            
            data = []
            for lead in leads:
                data.append({
                    'Lead ID': lead.lead_id,
                    'Client Name': lead.client_name or '',
                    'Architect Name': lead.architect_name or '',
                    'Firm Name': lead.firm_name or '',
                    'Grade': lead.grade or '',
                    'Client Type': lead.client_type or '',
                    'BD Name': lead.bd_name or '',
                    'BD Email': lead.bd_email or '',
                    'Client Mobile': lead.client_mobile or '',
                    'Address': lead.address or '',
                    'Meeting Date': lead.meeting_date.strftime("%Y-%m-%d") if lead.meeting_date else '',
                    'Meeting Time': lead.meeting_time.strftime("%H:%M") if lead.meeting_time else '',
                    'Remark': lead.remark or '',
                    'Assigned To': lead.assigned_to or '',
                    'Reschedule Date': lead.reschedule_date.strftime("%Y-%m-%d") if lead.reschedule_date else '',
                    'Reschedule Time': lead.reschedule_time.strftime("%H:%M") if lead.reschedule_time else '',
                    'Reschedule Remark': lead.reschedule_remark or '',
                    'Not Interested': 'Yes' if lead.not_interested else 'No',
                    'Not Interested Remark': lead.not_interested_remark or '',
                    'Require Letter': 'Yes' if lead.require_letter else 'No',
                    'Require Letter Remark': lead.require_letter_remark or '',
                    'Email Catalogue': 'Yes' if lead.email_catalogue else 'No',
                    'Email Catalogue Remark': lead.email_catalogue_remark or '',
                    'Quotation Sent': 'Yes' if lead.quotation_sent else 'No',
                    'Quotation Sent Remark': lead.quotation_sent_remark or '',
                    'Require Letter Followup': lead.require_letter_followup_date.strftime("%Y-%m-%d") if lead.require_letter_followup_date else '',
                    'Email Catalogue 1st Followup': lead.email_catalogue_followup_date.strftime("%Y-%m-%d") if lead.email_catalogue_followup_date else '',
                    'Email Catalogue 2nd Followup': lead.email_catalogue_second_followup_date.strftime("%Y-%m-%d") if lead.email_catalogue_second_followup_date else '',
                    'Quotation Followup': lead.quotation_followup_date.strftime("%Y-%m-%d") if lead.quotation_followup_date else '',
                    'Last Update': lead.last_followup_update or '',
                    'Created At': lead.created_at.strftime("%Y-%m-%d %H:%M:%S") if lead.created_at else '',
                    'Updated At': lead.updated_at.strftime("%Y-%m-%d %H:%M:%S") if lead.updated_at else ''
                })
            
            df = pd.DataFrame(data)
            
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='Leads Data', index=False)
                
                workbook = writer.book
                worksheet = writer.sheets['Leads Data']
                
                header_format = workbook.add_format({
                    'bold': True,
                    'text_wrap': True,
                    'valign': 'top',
                    'fg_color': '#D7E4BC',
                    'border': 1
                })
                
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                
                for i, col in enumerate(df.columns):
                    max_length = max(df[col].astype(str).map(len).max(), len(col)) + 2
                    worksheet.set_column(i, i, min(max_length, 50))
            
            output.seek(0)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if export_type == "date_range":
                filename = f"leads_data_{start_date}_to_{end_date}_{timestamp}.xlsx"
            elif export_type == "created_range":
                filename = f"leads_created_{start_date}_to_{end_date}_{timestamp}.xlsx"
            else:
                filename = f"all_leads_data_{timestamp}.xlsx"
            
            response = make_response(output.read())
            response.headers['Content-Disposition'] = f'attachment; filename={filename}'
            response.headers['Content-type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            
            return response
            
        except Exception as e:
            flash(f"Error exporting data: {str(e)}")
    
    total_leads = Lead.query.count()
    today = date.today()
    this_month_leads = Lead.query.filter(
        Lead.created_at >= datetime(today.year, today.month, 1)
    ).count()
    
    content = f"""
    <div class="card">
        <h2>Export Data to Excel</h2>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0;">
            <div style="background: #3498db; color: white; padding: 20px; border-radius: 8px; text-align: center;">
                <h3 style="margin: 0;">{total_leads}</h3>
                <p style="margin: 5px 0 0 0;">Total Leads</p>
            </div>
            <div style="background: #27ae60; color: white; padding: 20px; border-radius: 8px; text-align: center;">
                <h3 style="margin: 0;">{this_month_leads}</h3>
                <p style="margin: 5px 0 0 0;">This Month</p>
            </div>
        </div>
        
        <form method="post">
            <div class="form-group">
                <label for="export_type">Export Type:</label>
                <select id="export_type" name="export_type" onchange="toggleDateFields()" required>
                    <option value="all">All Leads</option>
                    <option value="date_range">By Meeting Date Range</option>
                    <option value="created_range">By Creation Date Range</option>
                </select>
            </div>
            
            <div id="date_fields" style="display: none;">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div class="form-group">
                        <label for="start_date">Start Date:</label>
                        <input type="date" id="start_date" name="start_date">
                    </div>
                    <div class="form-group">
                        <label for="end_date">End Date:</label>
                        <input type="date" id="end_date" name="end_date">
                    </div>
                </div>
            </div>
            
            <button type="submit" style="background: #27ae60;">
                📤 Export to Excel
            </button>
        </form>
        
        <div style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 5px; border-left: 4px solid #3498db;">
            <h4 style="margin: 0 0 10px 0;">Export Information:</h4>
            <ul style="margin: 0; padding-left: 20px;">
                <li><strong>All Leads:</strong> Exports all leads data</li>
                <li><strong>By Meeting Date Range:</strong> Exports leads with meeting dates in the specified range</li>
                <li><strong>By Creation Date Range:</strong> Exports leads created in the specified date range</li>
            </ul>
            <p style="margin: 10px 0 0 0;"><strong>Note:</strong> The Excel file will include all lead details including client name, mobile, address, meeting information, follow-up dates, remarks, and status updates.</p>
        </div>
    </div>
    
    <script>
        function toggleDateFields() {{
            const exportType = document.getElementById('export_type').value;
            const dateFields = document.getElementById('date_fields');
            const startDate = document.getElementById('start_date');
            const endDate = document.getElementById('end_date');
            
            if (exportType === 'all') {{
                dateFields.style.display = 'none';
                startDate.required = false;
                endDate.required = false;
            }} else {{
                dateFields.style.display = 'block';
                startDate.required = true;
                endDate.required = true;
            }}
        }}
        
        const today = new Date().toISOString().split('T')[0];
        document.getElementById('end_date').value = today;
        
        const thirtyDaysAgo = new Date();
        thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
        document.getElementById('start_date').value = thirtyDaysAgo.toISOString().split('T')[0];
    </script>
    """
    
    return render_page(content, "Export Data - CRM")

# -------------------------------
# MANAGE USERS
# -------------------------------
@app.route("/manage_users", methods=["GET", "POST"])
@login_required
@admin_required
def manage_users():
    users = User.query.all()
    
    if request.method == "POST":
        try:
            username = request.form.get("username", "").strip()
            password = request.form.get("password")
            role = request.form.get("role")
            
            if not username or not password:
                flash("Username and password are required")
            elif User.query.filter_by(username=username).first():
                flash("Username already exists")
            else:
                user = User(username=username, role=role)
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                flash(f"User {username} added successfully!", "success")
                return redirect(url_for("manage_users"))
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding user: {str(e)}")
    
    content = """
    <div class="card">
        <h2>Manage Users</h2>
        <form method="post">
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px;">
                <div class="form-group">
                    <label for="username">Username *:</label>
                    <input type="text" id="username" name="username" required>
                </div>
                <div class="form-group">
                    <label for="password">Password *:</label>
                    <input type="password" id="password" name="password" required>
                </div>
                <div class="form-group">
                    <label for="role">Role:</label>
                    <select id="role" name="role">
                        <option value="admin">Admin</option>
                        <option value="bd">BD</option>
                        <option value="user">User</option>
                    </select>
                </div>
            </div>
            <button type="submit">Add User</button>
        </form>
    </div>
    
    <div class="card">
        <h3>Existing Users</h3>
        <table>
            <thead>
                <tr>
                    <th>Username</th>
                    <th>Role</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for user in users:
        content += f"""
                <tr>
                    <td>{user.username}</td>
                    <td>{user.role.upper()}</td>
                    <td>
                        {"Protected Admin" if user.username == "admin" else "Active"}
                    </td>
                </tr>
        """
    
    content += """
            </tbody>
        </table>
    </div>
    """
    
    return render_page(content, "Manage Users - CRM")


# -------------------------------
# ERROR HANDLERS
# -------------------------------
@app.errorhandler(404)
def not_found(error):
    return render_page("""
    <div class="card" style="text-align: center;">
        <h2>Page Not Found</h2>
        <a href="/dashboard">Go to Dashboard</a>
    </div>""", "404 - Not Found"), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_page("""
    <div class="card" style="text-align: center;">
        <h2>Internal Server Error</h2>
        <a href="/dashboard">Go to Dashboard</a>
    </div>""", "500 - Error"), 500


# -------------------------------
# RUN APP
# -------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5001, use_reloader=False)     