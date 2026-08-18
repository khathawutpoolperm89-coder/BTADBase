import requests
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

app = Flask(__name__)
app.secret_key = 'super_secret_key_student_app'

# ตรวจสอบว่า URL นี้เปิดใน Browser แล้วเห็นข้อมูล JSON หรือไม่?
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxECb2v3avtM8sFb8lruYSlf-PybV3cazw2orggnzsVmjMhhwOgxj3vgkWmvcdLpq_5/exec"

def get_student_data():
    try:
        response = requests.get(APPS_SCRIPT_URL)
        if response.status_code == 200:
            return response.json()
        print("Error: Status Code", response.status_code)
        return []
    except Exception as e:
        print("Error fetching data:", e)
        return []
@app.route('/login_staff', methods=['POST'])
def login_staff():
    data = request.json
    role = data.get('role')
    username = data.get('username')
    password = data.get('password')
    
    # 🔴 ตัวอย่างตรวจสอบรหัสแบบตั้งค่าไว้ในโค้ด (หรือจะดึงจาก Sheets ก็ได้)
    if role == 'teacher' and username == 'teacher' and password == '1234':
        session['role'] = 'teacher'
        session['fullname'] = 'อาจารย์ผู้ดูแล'
        return jsonify({"success": True, "redirect_url": "/teacher_dashboard"})
        
    elif role == 'admin' and username == 'admin' and password == 'admin1234':
        session['role'] = 'admin'
        session['fullname'] = 'ผู้ดูแลระบบสูงสุด'
        return jsonify({"success": True, "redirect_url": "/admin_dashboard"})
        
    return jsonify({"success": False, "message": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"})
@app.route('/')
def login_page():
    if 'fullname' in session:
        return redirect(url_for('dashboard'))
        
    records = get_student_data()
    
    classes = set()
    all_students = []
    
    if records and isinstance(records, list):
        for row in records:
            student_class = ""
            student_name = ""
            for k, v in row.items():
                if 'class' in str(k).lower() and v:
                    student_class = str(v).strip()
                    classes.add(student_class)
                if 'fullname' in str(k).lower() or 'name' in str(k).lower():
                    student_name = str(v).strip()
            
            if student_class and student_name:
                all_students.append({
                    "class": student_class,
                    "name": student_name
                })
                    
    sorted_classes = sorted(list(classes))
    return render_template('login.html', classes=sorted_classes, all_students=all_students)
@app.route('/get_students_by_class', methods=['POST'])
def get_students_by_class():
    selected_class = request.json.get('class_name')
    records = get_student_data()
    filtered_students = []
    
    if records and isinstance(records, list):
        for row in records:
            # ค้นหา key ที่เก็บ class และ name
            student_class = ""
            student_name = ""
            for k, v in row.items():
                if 'class' in str(k).lower(): student_class = str(v).strip()
                if 'name' in str(k).lower(): student_name = str(v).strip()
            
            if student_class == selected_class:
                filtered_students.append(student_name)
    return jsonify({"students": filtered_students})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    selected_name = data.get('fullname')
    entered_pin = data.get('pin')
    records = get_student_data()
    student = None
    
    # ค้นหาข้อมูลนักเรียน
    for row in records:
        for k, v in row.items():
            if 'name' in str(k).lower() and str(v).strip() == selected_name:
                student = row
                break
    
    if student:
        # ค้นหา student_id
        student_id_val = ""
        for k, v in student.items():
            if 'id' in str(k).lower() and 'national' not in str(k).lower():
                student_id_val = str(v).strip()
        
        last_4 = student_id_val[-4:] if len(student_id_val) >= 4 else student_id_val
        
        if entered_pin == last_4:
            session['fullname'] = selected_name
            session['student_id'] = student_id_val
            return jsonify({"success": True, "message": "สำเร็จ"})
        else:
            return jsonify({"success": False, "message": "รหัสผ่านไม่ถูกต้อง"})
            
    return jsonify({"success": False, "message": "ไม่พบข้อมูล"})

@app.route('/dashboard')
def dashboard():
    if 'fullname' not in session:
        return redirect(url_for('login_page'))
    
    student_data = {
        "name": session['fullname'],
        "room": session.get('room', '-'),
        "next_class": {"subject": "อินเทอร์เน็ตในงานธุรกิจดิจิทัล", "time": "10:30 - 11:20", "room": "คอมฯ 1"},
        "today_schedule": [
            {"period": 1, "time": "08:30-09:20", "subject": "คณิตศาสตร์"},
            {"period": 2, "time": "09:20-10:10", "subject": "ภาษาอังกฤษ"},
            {"period": 3, "time": "10:30-11:20", "subject": "อินเทอร์เน็ตในงานธุรกิจดิจิทัล"},
            {"period": 4, "time": "11:20-12:10", "subject": "พักกลางวัน"},
            {"period": 5, "time": "12:10-13:00", "subject": "วิทยาศาสตร์"}
        ],
        "assignments": [
            {"task": "ออกแบบเว็บไซต์ E-commerce", "due": "15 ส.ค.", "status": "ค้างส่ง"},
            {"task": "แบบฝึกหัดคณิต หน้า 45", "due": "16 ส.ค.", "status": "ค้างส่ง"}
        ],
        "grades": [
            {"subject": "คณิตศาสตร์", "grade": "3.5"},
            {"subject": "วิทยาศาสตร์", "grade": "4.0"},
            {"subject": "ภาษาอังกฤษ", "grade": "3.0"}
        ]
    }
    
    return render_template('dashboard.html', data=student_data)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)