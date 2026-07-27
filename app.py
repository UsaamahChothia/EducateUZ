from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'educate_uz_secure_key_2026' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///educateuz.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- SCHOOL SUBJECTS CONFIGURATION ---
# Grouped by academic phases for organized frontend selection
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
    status = db.Column(db.String(20), default='Searching')
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    tutor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    zoom_link = db.Column(db.String(200))
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    final_price = db.Column(db.Float, default=0.0)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- AUTH ROUTES ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        hashed_pw = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
        role = request.form.get('role')
        is_val = True if role == 'Student' else False
        new_user = User(email=request.form.get('email'), password=hashed_pw, role=role, qualifications=request.form.get('qualifications'), is_verified=is_val)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email')).first()
        if user and bcrypt.check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            if user.email == 'uchothia16@gmail.com':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- NAVIGATION ROUTES ---

@app.route('/')
@login_required
def index():
    if current_user.role == 'Tutor' and current_user.email != 'uchothia16@gmail.com':
        return redirect(url_for('tutor_dashboard'))
    # Pass the schools dictionary to index.html (the student dashboard)
    return render_template('index.html', subjects=SCHOOL_SUBJECTS)

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.email != 'uchothia16@gmail.com':
        return "Unauthorized", 403
    pending_tutors = User.query.filter_by(role='Tutor', is_verified=False).all()
    active_sessions = Session.query.filter(Session.status.in_(['Searching', 'Active'])).all()
    total_rev = db.session.query(db.func.sum(Session.final_price)).scalar() or 0
    return render_template('admin_dashboard.html', tutors=pending_tutors, sessions=active_sessions, revenue=total_rev)

# --- SESSION LOGIC ---

@app.route('/request_tutor', methods=['POST'])
@login_required
def request_tutor():
    new_session = Session(subject=request.form.get('subject'), student_id=current_user.id)
    db.session.add(new_session)
    db.session.commit()
    return redirect(url_for('waiting_room', session_id=new_session.id))

@app.route('/waiting_room/<int:session_id>')
@login_required
def waiting_room(session_id):
    session_data = Session.query.get(session_id)
    return render_template('waiting_room.html', session=session_data)

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
    session_to_update = Session.query.get(session_id)
    if session_to_update:
        session_to_update.status = 'Active'
        session_to_update.tutor_id = current_user.id
        session_to_update.start_time = datetime.utcnow()
        session_to_update.zoom_link = "https://zoom.us/j/test_meeting"
        db.session.commit()
    return redirect(url_for('tutor_dashboard'))

@app.route('/end_session/<int:session_id>', methods=['POST'])
@login_required
def end_session(session_id):
    session_to_update = Session.query.get(session_id)
    if session_to_update:
        session_to_update.status = 'Completed'
        session_to_update.end_time = datetime.utcnow()
        duration = session_to_update.end_time - session_to_update.start_time
        minutes = max(1, duration.total_seconds() / 60)
        session_to_update.final_price = round(minutes * 5.0, 2)
        db.session.commit()
    return redirect(url_for('tutor_dashboard'))

@app.route('/admin/approve/<int:user_id>', methods=['POST'])
@login_required
def approve_tutor(user_id):
    user = User.query.get(user_id)
    if user and current_user.email == 'uchothia16@gmail.com':
        user.is_verified = True
        db.session.commit()
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
