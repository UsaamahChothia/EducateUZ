import os
import requests
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'educate_uz_secure_key_2026')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///educateuz.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- SCHOOL SUBJECTS CONFIGURATION ---
SCHOOL_SUBJECTS = {
    "Senior Phase (Grades 7-9)": [
        "Mathematics (Grades 7-9)",
        "Natural Sciences",
        "Technology",
        "Economic and Management Sciences (EMS)",
        "English Home Language",
        "Afrikaans First Additional Language",
        "Social Sciences (History & Geography)"
    ],
    "FET Phase (Grades 10-12)": [
        "Mathematics (Core)",
        "Mathematical Literacy",
        "Physical Sciences",
        "Life Sciences",
        "Accounting",
        "Business Studies",
        "Economics",
        "Geography",
        "History",
        "Information Technology (IT)",
        "Computer Applications Technology (CAT)"
    ]
}

# --- DATABASE MODELS ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(20), nullable=False) 
    qualifications = db.Column(db.Text) 
    is_verified = db.Column(db.Boolean, default=False) 

class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100))
    status = db.Column(db.String(20), default='Searching')  # Searching, Active, Completed, Cancelled
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    tutor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    zoom_link = db.Column(db.String(300))
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    final_price = db.Column(db.Float, default=0.0)

    student = db.relationship('User', foreign_keys=[student_id], backref='student_sessions')
    tutor = db.relationship('User', foreign_keys=[tutor_id], backref='tutor_sessions')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ZOOM API SERVICE ---
def create_zoom_meeting(topic="EducateUZ Live Session"):
    account_id = os.getenv("ZOOM_ACCOUNT_ID")
    client_id = os.getenv("ZOOM_CLIENT_ID")
    client_secret = os.getenv("ZOOM_CLIENT_SECRET")

    # If credentials are not set, return a realistic dynamic test link for safe offline demos
    if not (account_id and client_id and client_secret):
        mock_meeting_id = int(datetime.utcnow().timestamp())
        return f"https://zoom.us/j/{mock_meeting_id}?pwd=UZ{mock_meeting_id % 10000}"

    try:
        token_url = "https://zoom.us/oauth/token"
        params = {
            "grant_type": "account_credentials",
            "account_id": account_id
        }
        auth_response = requests.post(
            token_url,
            params=params,
            auth=(client_id, client_secret),
            timeout=8
        )
        auth_data = auth_response.json()
        access_token = auth_data.get("access_token")
        if not access_token:
            raise ValueError("Could not retrieve Zoom access token.")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        meeting_url = "https://api.zoom.us/v2/users/me/meetings"
        payload = {
            "topic": topic,
            "type": 1,  # Instant meeting
            "settings": {
                "host_video": True,
                "participant_video": True,
                "join_before_host": True,
                "waiting_room": False
            }
        }
        meeting_response = requests.post(meeting_url, headers=headers, json=payload, timeout=8)
        meeting_data = meeting_response.json()
        return meeting_data.get("join_url")
    except Exception as e:
        print(f"Zoom API Error: {e}")
        mock_id = int(datetime.utcnow().timestamp())
        return f"https://zoom.us/j/{mock_id}?pwd=UZ{mock_id % 10000}"

# --- AUTH ROUTES ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        raw_pw = request.form.get('password')
        role = request.form.get('role', 'Student')
        quals = request.form.get('qualifications', '')

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))

        hashed_pw = bcrypt.generate_password_hash(raw_pw).decode('utf-8')
        is_val = True if role == 'Student' else False
        new_user = User(email=email, password=hashed_pw, role=role, qualifications=quals, is_verified=is_val)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            if user.email == 'uchothia16@gmail.com':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('index'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- CORE NAVIGATION ROUTES ---
@app.route('/')
@login_required
def index():
    if current_user.role == 'Tutor' and current_user.email != 'uchothia16@gmail.com':
        return redirect(url_for('tutor_dashboard'))
    return render_template('index.html', subjects=SCHOOL_SUBJECTS)

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.email != 'uchothia16@gmail.com':
        return "Unauthorized", 403
    pending_tutors = User.query.filter_by(role='Tutor', is_verified=False).all()
    active_sessions = Session.query.filter(Session.status.in_(['Searching', 'Active'])).all()
    total_rev = db.session.query(db.func.sum(Session.final_price)).scalar() or 0.0
    return render_template('admin_dashboard.html', tutors=pending_tutors, sessions=active_sessions, revenue=round(total_rev, 2))

# --- SESSION & BOOKING LOGIC ---
@app.route('/request_tutor', methods=['POST'])
@login_required
def request_tutor():
    subject = request.form.get('subject')
    new_session = Session(subject=subject, student_id=current_user.id, status='Searching')
    db.session.add(new_session)
    db.session.commit()
    return redirect(url_for('waiting_room', session_id=new_session.id))

@app.route('/waiting_room/<int:session_id>')
@login_required
def waiting_room(session_id):
    session_data = Session.query.get_or_404(session_id)
    return render_template('waiting_room.html', session=session_data)

# Real-time polling API endpoint for smooth waiting room updates
@app.route('/api/session_status/<int:session_id>')
@login_required
def session_status_api(session_id):
    session_data = Session.query.get_or_404(session_id)
    tutor_name = session_data.tutor.email if session_data.tutor else None
    return jsonify({
        'status': session_data.status,
        'zoom_link': session_data.zoom_link,
        'final_price': session_data.final_price,
        'tutor': tutor_name
    })

@app.route('/cancel_session/<int:session_id>', methods=['POST'])
@login_required
def cancel_session(session_id):
    session_data = Session.query.get_or_404(session_id)
    if session_data.student_id == current_user.id and session_data.status == 'Searching':
        session_data.status = 'Cancelled'
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/tutor')
@login_required
def tutor_dashboard():
    if not current_user.is_verified and current_user.email != 'uchothia16@gmail.com':
        return render_template('pending_tutor.html')
    open_reqs = Session.query.filter_by(status='Searching').all()
    my_active = Session.query.filter_by(tutor_id=current_user.id, status='Active').all()
    return render_template('tutor.html', sessions=open_reqs, active_sessions=my_active)

@app.route('/accept_session/<int:session_id>', methods=['POST'])
@login_required
def accept_session(session_id):
    session_to_update = Session.query.get_or_404(session_id)
    if session_to_update.status == 'Searching':
        session_to_update.status = 'Active'
        session_to_update.tutor_id = current_user.id
        session_to_update.start_time = datetime.utcnow()
        session_to_update.zoom_link = create_zoom_meeting(f"EducateUZ: {session_to_update.subject}")
        db.session.commit()
    return redirect(url_for('tutor_dashboard'))

@app.route('/end_session/<int:session_id>', methods=['POST'])
@login_required
def end_session(session_id):
    session_to_update = Session.query.get_or_404(session_id)
    if session_to_update and session_to_update.tutor_id == current_user.id:
        session_to_update.status = 'Completed'
        session_to_update.end_time = datetime.utcnow()
        start = session_to_update.start_time or datetime.utcnow()
        duration = session_to_update.end_time - start
        minutes = max(1, duration.total_seconds() / 60)
        # R5.00 per minute = R300.00/hour
        session_to_update.final_price = round(minutes * 5.0, 2)
        db.session.commit()
    return redirect(url_for('tutor_dashboard'))

@app.route('/admin/approve/<int:user_id>', methods=['POST'])
@login_required
def approve_tutor(user_id):
    if current_user.email != 'uchothia16@gmail.com':
        return "Unauthorized", 403
    user = User.query.get_or_404(user_id)
    user.is_verified = True
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

# --- DEMO SEED CLI COMMAND ---
@app.cli.command("seed-db")
def seed_db():
    """Populates the database with verified demo tutors and sample subjects."""
    db.create_all()
    demo_tutors = [
        {"email": "tutor.sarah@educateuz.co.za", "quals": "BSc Mathematics & Statistics, 3 years IEB/CAPS tutoring"},
        {"email": "tutor.david@educateuz.co.za", "quals": "BCom Accounting Honours, CA(SA) Trainee, High School Accounting expert"},
        {"email": "tutor.lerato@educateuz.co.za", "quals": "BEng Chemical Engineering, Physical Sciences & Core Math specialist"}
    ]
    for t in demo_tutors:
        if not User.query.filter_by(email=t["email"]).first():
            pw_hash = bcrypt.generate_password_hash("demo1234").decode('utf-8')
            user = User(email=t["email"], password=pw_hash, role="Tutor", qualifications=t["quals"], is_verified=True)
            db.session.add(user)
    db.session.commit()
    print("Database seeded with demo verified tutors (password: demo1234).")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)