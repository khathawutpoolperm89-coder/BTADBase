import requests
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

app = Flask(__name__)
app.secret_key = 'super_secret_key_student_app'

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

@app.route('/')
def login_page():
    if 'fullname' in session:
        # แยก Redirect ตามบทบาทที่ล็อกอินค้างไว้
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif session.get('role') == 'teacher':
            return redirect(url_for('teacher_dashboard'))
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

@app.route('/login_staff', methods=['POST'])
def login_staff():
    try:
        data = request.json
        role = data.get('role')
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        # ดึงข้อมูล Staff ทั้งหมดจาก Google Sheets
        res = requests.get(f"{APPS_SCRIPT_URL}?action=getStaff", allow_redirects=True)
        staff_list = res.json()

        # ตรวจสอบ Username, Password และ Role
        user = next((s for s in staff_list if str(s['username']) == username and str(s['password']) == password and str(s['role']) == role), None)

        if user:
            session['role'] = user['role']
            session['fullname'] = user['fullname']
            
            redirect_url = '/admin_dashboard' if role == 'admin' else '/teacher_dashboard'
            return jsonify({"success": True, "redirect_url": redirect_url})
            
        return jsonify({"success": False, "message": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"})
    except Exception as e:
        return jsonify({"success": False, "message": f"เกิดข้อผิดพลาด: {str(e)}"}), 500

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    selected_name = data.get('fullname')
    entered_pin = data.get('pin')
    records = get_student_data()
    student = None
    
    for row in records:
        for k, v in row.items():
            if 'name' in str(k).lower() and str(v).strip() == selected_name:
                student = row
                break
    
    if student:
        student_id_val = ""
        for k, v in student.items():
            if 'id' in str(k).lower() and 'national' not in str(k).lower():
                student_id_val = str(v).strip()
        
        last_4 = student_id_val[-4:] if len(student_id_val) >= 4 else student_id_val
        
        if entered_pin == last_4:
            session['role'] = 'student'
            session['fullname'] = selected_name
            session['student_id'] = student_id_val
            return jsonify({"success": True, "message": "สำเร็จ"})
        else:
            return jsonify({"success": False, "message": "รหัสผ่านไม่ถูกต้อง"})
            
    return jsonify({"success": False, "message": "ไม่พบข้อมูล"})

# 🔵 [เพิ่มใหม่] หน้า Admin Dashboard
@app.route('/admin_dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('login_page'))
    return render_template('admin_dashboard.html')

# 🔵 [เพิ่มใหม่] API ดึงรายชื่อ Staff ไปแสดงในตารางหน้า Admin
@app.route('/get_staff_list')
def get_staff_list():
    if session.get('role') != 'admin':
        return jsonify([])
    res = requests.get(f"{APPS_SCRIPT_URL}?action=getStaff")
    return jsonify(res.json())

@app.route('/create_teacher', methods=['POST'])
def create_teacher():
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "คุณไม่มีสิทธิ์ในการดำเนินการนี้"}), 403

    data = request.json
    username = data.get('username')
    password = data.get('password')
    fullname = data.get('fullname')

    if not username or not password or not fullname:
        return jsonify({"success": False, "message": "กรุณากรอกข้อมูลให้ครบถ้วน"})

    payload = {
        'action': 'addTeacher',
        'username': username,
        'password': password,
        'fullname': fullname
    }
    requests.get(APPS_SCRIPT_URL, params=payload)

    return jsonify({"success": True, "message": "สร้างบัญชีอาจารย์เรียบร้อยแล้ว!"})

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
# 🔵 หน้า Teacher Dashboard (ตรวจสอบสิทธิ์ต้องเป็น teacher เท่านั้น)
@app.route('/teacher_dashboard')
def teacher_dashboard():
    if session.get('role') != 'teacher':
        return redirect(url_for('login_page'))

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
    return render_template('teacher_dashboard.html', classes=sorted_classes, all_students=all_students)
# 🔵 หน้าสรุปรายงานการเข้าเรียน (Report Dashboard)
@app.route('/report')
def report():
    if 'fullname' not in session:
        return redirect(url_for('login_page'))

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
    return render_template('report.html', classes=sorted_classes, all_students=all_students)
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)