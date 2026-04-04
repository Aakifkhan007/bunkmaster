import os
import math
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = "bunkmaster-secure-key-2026"

# ── Database Configuration ──
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ── Models ──
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rollno = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password = db.Column(db.String(100), nullable=False)
    course = db.Column(db.String(100), default="B.Tech CSE")
    year = db.Column(db.String(10), default="3rd")
    dept = db.Column(db.String(100), default="Computer Science")

class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empid = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(100), nullable=False)
    dept = db.Column(db.String(100), default="Computer Science")
    # NEW: Link teacher to a specific subject code
    subject_code = db.Column(db.String(20), nullable=False) 

class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_rollno = db.Column(db.String(20), nullable=False)
    subject_code = db.Column(db.String(20), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    status = db.Column(db.Integer, nullable=False)

# ── Static Metadata (Used for Names and Dropdowns) ──
SUBJECTS_META = {
    "MA301": {"name": "Engineering Mathematics III", "code": "MA301"},
    "CS202": {"name": "Data Structures & Algorithms", "code": "CS202"},
    "CS303": {"name": "Operating Systems", "code": "CS303"},
    "CS404": {"name": "Computer Networks", "code": "CS404"},
    "CS505": {"name": "Machine Learning", "code": "CS505"},
}

# ── Logic Helpers ──
def enrich_student_data(rollno):
    enriched = []
    for code, meta in SUBJECTS_META.items():
        # FIND THE REAL TEACHER for this subject from DB
        teacher_obj = Teacher.query.filter_by(subject_code=code).first()
        teacher_name = teacher_obj.name if teacher_obj else "TBA"
        
        records = AttendanceRecord.query.filter_by(student_rollno=rollno, subject_code=code).all()
        attended = sum(1 for r in records if r.status == 1)
        total = len(records)
        pct = round(attended / total * 100, 1) if total > 0 else 0
        is_safe = pct >= 75
        bunk = int((attended - 0.75 * total) / 0.75) if is_safe and total > 0 else 0
        need = math.ceil((0.75 * total - attended) / 0.25) if not is_safe and total > 0 else 0
        
        enriched.append({
            **meta, 
            "teacher": teacher_name, # Dynamically assigned name
            "calendar": [{"date": r.date, "status": r.status} for r in records], 
            "attended": attended, "total": total, "percent": pct, 
            "is_safe": is_safe, "bunk_count": bunk, "need_count": need
        })
    return enriched

# ── Routes ──

@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("student_dashboard" if session["role"] == "student" else "teacher_dashboard"))
    return render_template("role_select.html")

@app.route("/signup/student", methods=["GET", "POST"])
def signup_student():
    if request.method == "POST":
        rollno = request.form.get("rollno").strip()
        if Student.query.filter_by(rollno=rollno).first():
            flash("Roll Number already registered", "error")
            return redirect(url_for("signup_student"))
        new_s = Student(
            rollno=rollno, 
            name=request.form.get("name"), 
            email=request.form.get("email"), 
            password=request.form.get("password"),
            course=request.form.get("course", "B.Tech CSE")
        )
        db.session.add(new_s); db.session.commit()
        return redirect(url_for("login_student"))
    return render_template("signup_student.html")

@app.route("/signup/teacher", methods=["GET", "POST"])
def signup_teacher():
    if request.method == "POST":
        empid = request.form.get("empid").strip()
        if Teacher.query.filter_by(empid=empid).first():
            flash("ID already registered", "error")
            return redirect(url_for("signup_teacher"))
        
        new_t = Teacher(
            empid=empid, 
            name=request.form.get("name"), 
            password=request.form.get("password"),
            dept=request.form.get("dept", "Computer Science"),
            subject_code=request.form.get("subject_code") # CAPTURE THE SUBJECT
        )
        db.session.add(new_t); db.session.commit()
        return redirect(url_for("login_teacher"))
    # Pass subjects to the signup page for the dropdown
    return render_template("signup_teacher.html", subjects=SUBJECTS_META.values())

@app.route("/login/student", methods=["GET", "POST"])
def login_student():
    if request.method == "POST":
        user = Student.query.filter_by(rollno=request.form.get("rollno"), password=request.form.get("password")).first()
        if user:
            session.update({"user": user.rollno, "role": "student", "name": user.name})
            return redirect(url_for("student_dashboard"))
        flash("Invalid Credentials", "error")
    return render_template("login_student.html")

@app.route("/login/teacher", methods=["GET", "POST"])
def login_teacher():
    if request.method == "POST":
        user = Teacher.query.filter_by(empid=request.form.get("empid"), password=request.form.get("password")).first()
        if user:
            # Store their subject in session so we can lock their attendance page
            session.update({
                "user": user.empid, 
                "role": "teacher", 
                "name": user.name, 
                "subject_code": user.subject_code 
            })
            return redirect(url_for("teacher_dashboard"))
        flash("Invalid Credentials", "error")
    return render_template("login_teacher.html")

@app.route("/dashboard")
def student_dashboard():
    if session.get("role") != "student": return redirect(url_for("index"))
    user = Student.query.filter_by(rollno=session["user"]).first()
    if not user: session.clear(); return redirect(url_for("index"))
    subjects = enrich_student_data(session["user"])
    safe = sum(1 for s in subjects if s["is_safe"])
    total_cls = sum(s["total"] for s in subjects)
    overall = round(sum(s["attended"] for s in subjects) / total_cls * 100, 1) if total_cls > 0 else 0
    return render_template("student_dashboard.html", student=user, subjects=subjects, safe_count=safe, warn_count=len(subjects)-safe, overall_pct=overall)

@app.route("/teacher")
def teacher_dashboard():
    if session.get("role") != "teacher": return redirect(url_for("index"))
    teacher = Teacher.query.filter_by(empid=session["user"]).first()
    if not teacher: session.clear(); return redirect(url_for("index"))
    
    all_st = Student.query.all()
    # ONLY SHOW STATS FOR THIS TEACHER'S SUBJECT
    sub_code = teacher.subject_code
    sub_meta = SUBJECTS_META.get(sub_code)
    
    safe_s, risky_s, risky_list = 0, 0, []
    
    for st in all_st:
        data = enrich_student_data(st.rollno)
        # Find the specific subject this teacher teaches
        target = next((s for s in data if s["code"] == sub_code), None)
        if target:
            if target["is_safe"]: safe_s += 1
            else: 
                risky_s += 1
                risky_list.append({
                    "name": st.name, "rollno": st.rollno, 
                    "subject": target["name"], "pct": target["percent"], 
                    "need": target["need_count"]
                })

    return render_template("teacher_dashboard.html", 
                           teacher=teacher, 
                           subjects=[{**sub_meta, "enrolled": len(all_st), "avg_pct": 75}], 
                           total_students=len(all_st), safe_students=safe_s, 
                           risky_students=risky_s, risky_list=risky_list)

@app.route("/teacher/mark", methods=["GET", "POST"])
def teacher_mark():
    if session.get("role") != "teacher": return redirect(url_for("index"))
    
    teacher = Teacher.query.filter_by(empid=session["user"]).first()
    students = Student.query.all()
    
    if request.method == "POST":
        # Teacher can ONLY mark their assigned subject
        sub = teacher.subject_code 
        dt = date.today().strftime("%b %d")
        for st in students:
            status_val = request.form.get(f"attendance_{st.rollno}")
            status = 1 if status_val == "present" else 0
            db.session.add(AttendanceRecord(student_rollno=st.rollno, subject_code=sub, date=dt, status=status))
        db.session.commit()
        flash(f"Attendance for {sub} marked successfully!", "success")
        return redirect(url_for("teacher_dashboard"))
        
    return render_template("teacher_mark.html", 
                           subject=SUBJECTS_META.get(teacher.subject_code), 
                           students=students, 
                           today=date.today().isoformat())
# Ensure there is a "/" before "teacher" and another before "students"
@app.route("/teacher/students")
def teacher_students():
    if session.get("role") != "teacher": 
        return redirect(url_for("index"))
    
    raw_students = Student.query.all()
    processed_students = []
    
    for s in raw_students:
        data = enrich_student_data(s.rollno)
        s_dict = {
            "name": s.name, 
            "rollno": s.rollno, 
            "course": s.course, 
            "subject_pcts": {item['code']: item['percent'] for item in data}, 
            "overall_pct": round(sum(item['percent'] for item in data) / len(data), 1) if data else 0
        }
        processed_students.append(s_dict)
    
    # Ensure you are passing SUBJECTS_META.values() so the table headers work!
    return render_template("teacher_students.html", 
                           students=processed_students, 
                           subjects=list(SUBJECTS_META.values()))

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("index"))

if __name__ == "__main__":
    with app.app_context(): db.create_all()
    app.run(debug=True, port=8080)