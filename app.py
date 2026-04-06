import os
import math
from datetime import datetime, date
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
    subject_code = db.Column(db.String(20), nullable=False) 

class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_rollno = db.Column(db.String(20), nullable=False)
    subject_code = db.Column(db.String(20), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(10), nullable=False) 

# ── Static Metadata ──
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
        teacher_obj = Teacher.query.filter_by(subject_code=code).first()
        teacher_name = teacher_obj.name if teacher_obj else "TBA"
        
        records = AttendanceRecord.query.filter_by(student_rollno=rollno, subject_code=code).all()
        
        attended = sum(1 for r in records if r.status == 'present')
        total = sum(1 for r in records if r.status in ['present', 'absent'])
        
        pct = round(attended / total * 100, 1) if total > 0 else 0
        is_safe = pct >= 75
        
        bunk = int((attended - 0.75 * total) / 0.75) if is_safe and total > 0 else 0
        need = math.ceil((0.75 * total - attended) / 0.25) if not is_safe and total > 0 else 0
        
        calendar_data = []
        for r in records:
            stat_map = {"present": 1, "absent": 0, "holiday": "GH"}
            calendar_data.append({"date": r.date, "status": stat_map.get(r.status, 0)})

        enriched.append({
            **meta, 
            "teacher": teacher_name,
            "calendar": calendar_data, 
            "attended": attended, "total": total, "percent": pct, 
            "is_safe": is_safe, "bunk_count": max(0, bunk), "need_count": max(0, need)
        })
    return enriched

# ── Routes ──

@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("student_dashboard" if session["role"] == "student" else "teacher_dashboard"))
    return render_template("role_select.html")

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
    subjects = enrich_student_data(session["user"])
    safe = sum(1 for s in subjects if s["is_safe"])
    total_cls = sum(s["total"] for s in subjects)
    overall = round(sum(s["attended"] for s in subjects) / total_cls * 100, 1) if total_cls > 0 else 0
    return render_template("student_dashboard.html", student=user, subjects=subjects, safe_count=safe, warn_count=len(subjects)-safe, overall_pct=overall)

@app.route("/teacher")
def teacher_dashboard():
    if session.get("role") != "teacher": return redirect(url_for("index"))
    teacher = Teacher.query.filter_by(empid=session["user"]).first()
    all_st = Student.query.all()
    sub_code = teacher.subject_code
    sub_meta = SUBJECTS_META.get(sub_code)
    
    safe_s, risky_s, risky_list = 0, 0, []
    for st in all_st:
        data = enrich_student_data(st.rollno)
        target = next((s for s in data if s["code"] == sub_code), None)
        if target:
            if target["is_safe"]: safe_s += 1
            else: 
                risky_s += 1
                risky_list.append({"name": st.name, "rollno": st.rollno, "pct": target["percent"], "need": target["need_count"]})

    return render_template("teacher_dashboard.html", teacher=teacher, subjects=[{**sub_meta, "enrolled": len(all_st)}], total_students=len(all_st), safe_students=safe_s, risky_students=risky_s, risky_list=risky_list)

@app.route("/teacher/mark", methods=["GET", "POST"])
def teacher_mark():
    if session.get("role") != "teacher": return redirect(url_for("index"))
    teacher = Teacher.query.filter_by(empid=session["user"]).first()
    students = Student.query.all()
    
    if request.method == "POST":
        sub = teacher.subject_code 
        raw_date = request.form.get("date")
        formatted_date = datetime.strptime(raw_date, '%Y-%m-%d').strftime("%b %d")

        for st in students:
            status = request.form.get(f"attendance_{st.rollno}")
            existing = AttendanceRecord.query.filter_by(student_rollno=st.rollno, subject_code=sub, date=formatted_date).first()
            if existing: existing.status = status
            else: db.session.add(AttendanceRecord(student_rollno=st.rollno, subject_code=sub, date=formatted_date, status=status))
                
        db.session.commit()
        flash(f"Attendance for {formatted_date} saved!", "success")
        return redirect(url_for("teacher_dashboard"))
        
    return render_template("teacher_mark.html", subject=SUBJECTS_META.get(teacher.subject_code), students=students, today=date.today().isoformat())

# ── NEW ROUTE: ENROLLED STUDENTS ──
@app.route("/teacher/students")
def teacher_students():
    if session.get("role") != "teacher": return redirect(url_for("index"))
    
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
    
    return render_template("teacher_students.html", 
                           students=processed_students, 
                           subjects=list(SUBJECTS_META.values()))

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("index"))

if __name__ == "__main__":
    with app.app_context(): db.create_all()
    app.run(debug=True, port=8080)