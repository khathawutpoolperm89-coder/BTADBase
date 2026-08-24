import os
import csv
import io
import re
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

app = Flask(__name__)
app.secret_key = 'super_secret_key_student_app'

# 🐘 ดึง Connection String ของ Neon จาก Environment Variable
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# ---------------------------------------------------------
# 🟢 1. ระบบ Login & หน้าหลัก
# ---------------------------------------------------------

@app.route('/')
def login_page():
    if 'fullname' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif session.get('role') == 'teacher':
            return redirect(url_for('teacher_dashboard'))
        return redirect(url_for('dashboard'))
        
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT fullname, class FROM students ORDER BY class, fullname")
    all_students = cur.fetchall()
    
    classes = sorted(list(set(s['class'] for s in all_students)))
    cur.close()
    conn.close()
    
    return render_template('login.html', classes=classes, all_students=all_students)

@app.route('/login', methods=['POST'])
def login():
    data = request.json or {}
    selected_name = data.get('fullname')
    entered_pin = data.get('pin')

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE fullname = %s", (selected_name,))
    student = cur.fetchone()
    cur.close()
    conn.close()

    if student:
        student_id_val = str(student['student_id'])
        last_4 = student_id_val[-4:] if len(student_id_val) >= 4 else student_id_val
        
        if entered_pin == last_4:
            session['role'] = 'student'
            session['fullname'] = student['fullname']
            session['student_id'] = student['student_id']
            session['student_room'] = student['class']
            return jsonify({"success": True, "message": "สำเร็จ"})
        return jsonify({"success": False, "message": "รหัสผ่านไม่ถูกต้อง"})
            
    return jsonify({"success": False, "message": "ไม่พบข้อมูล"})

@app.route('/login_staff', methods=['POST'])
def login_staff():
    try:
        data = request.json or {}
        role = str(data.get('role', '')).strip().lower()
        username = str(data.get('username', '')).strip()
        password = str(data.get('password', '')).strip()

        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM staff WHERE LOWER(username) = LOWER(%s) AND password = %s AND LOWER(role) = LOWER(%s)", (username, password, role))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            session['role'] = user['role']
            session['fullname'] = user['fullname']
            redirect_url = '/admin_dashboard' if role == 'admin' else '/teacher_dashboard'
            return jsonify({"success": True, "redirect_url": redirect_url})
            
        return jsonify({"success": False, "message": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"})
    except Exception as e:
        return jsonify({"success": False, "message": f"เกิดข้อผิดพลาด: {str(e)}"}), 500

# ---------------------------------------------------------
# 📥 2. API นำเข้านักเรียนจาก Google Sheet Link ลง Neon
# ---------------------------------------------------------

@app.route('/api/import_students_sheet', methods=['POST'])
def import_students_sheet():
    data = request.json or {}
    sheet_url = data.get('sheet_url')

    if not sheet_url:
        return jsonify({"success": False, "message": "กรุณาระบุ URL ของ Google Sheet"}), 400

    try:
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', sheet_url)
        if not match:
            return jsonify({"success": False, "message": "รูปแบบ URL ไม่ถูกต้อง"}), 400
        
        sheet_id = match.group(1)
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

        response = requests.get(csv_url, timeout=15)
        if response.status_code != 200:
            return jsonify({"success": False, "message": "เข้าถึง Sheet ไม่ได้ กรุณาตั้งค่าแชร์เป็น 'ทุกคนที่มีลิงก์'"}), 400

        csv_file = io.StringIO(response.content.decode('utf-8'))
        reader = csv.DictReader(csv_file)

        conn = get_db()
        cur = conn.cursor()
        count = 0
        for row in reader:
            s_id = str(row.get('student_id', '')).strip()
            fname = str(row.get('fullname', '')).strip()
            s_class = str(row.get('class', '')).strip()
            n_id = str(row.get('national_id', '')).strip() or None

            if s_id and fname and s_class:
                cur.execute("""
                    INSERT INTO students (student_id, fullname, class, national_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (student_id) DO UPDATE
                    SET fullname = EXCLUDED.fullname, class = EXCLUDED.class, national_id = EXCLUDED.national_id
                """, (s_id, fname, s_class, n_id))
                count += 1

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"success": True, "message": f"นำเข้าข้อมูลสำเร็จ {count} รายการ"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ---------------------------------------------------------
# 🎬 3. จัดการสื่อการสอน & แบบทดสอบ (Quiz)
# ---------------------------------------------------------

@app.route('/get_media', methods=['GET'])
def get_media():
    student_class = request.args.get('class', '')
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT m.id, m.subject, m.title, m.url, q.id AS quiz_id 
        FROM media m
        LEFT JOIN quizzes q ON m.id = q.media_id
        WHERE LOWER(m.class) = LOWER(%s) OR LOWER(m.class) = 'all' OR %s = ''
    """, (student_class, student_class))
    
    videos = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(videos)

@app.route('/save_media', methods=['POST'])
def save_media():
    data = request.json or {}
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO media (class, subject, title, url)
        VALUES (%s, %s, %s, %s)
    """, (data.get('class_name'), data.get('subject'), data.get('title'), data.get('video_url')))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True, "message": "บันทึกสื่อเรียบร้อยแล้ว"})

@app.route('/api/get_quiz/<int:quiz_id>', methods=['GET'])
def get_quiz(quiz_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, title, subject FROM quizzes WHERE id = %s", (quiz_id,))
    quiz = cur.fetchone()
    
    if not quiz:
        return jsonify({"success": False, "message": "ไม่พบข้อสอบ"}), 404
        
    cur.execute("SELECT id, question_text, option_a, option_b, option_c, option_d FROM questions WHERE quiz_id = %s", (quiz_id,))
    questions = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"success": True, "quiz": quiz, "questions": questions})

@app.route('/api/submit_quiz', methods=['POST'])
def submit_quiz():
    data = request.json or {}
    quiz_id = data.get('quiz_id')
    user_answers = data.get('answers', {})
    
    student_id = session.get('student_id', 'GUEST')
    student_name = session.get('fullname', 'ไม่ระบุชื่อ')

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, correct_option FROM questions WHERE quiz_id = %s", (quiz_id,))
    questions = cur.fetchall()
    
    score = 0
    total = len(questions)
    for q in questions:
        q_id = str(q['id'])
        if q_id in user_answers and user_answers[q_id] == q['correct_option']:
            score += 1

    cur.execute("""
        INSERT INTO quiz_scores (quiz_id, student_id, student_name, score, total_questions)
        VALUES (%s, %s, %s, %s, %s)
    """, (quiz_id, student_id, student_name, score, total))
    
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True, "score": score, "total": total})

# ---------------------------------------------------------
# 📝 4. บันทึกเช็คชื่อ & แดชบอร์ด
# ---------------------------------------------------------

@app.route('/save_attendance', methods=['POST'])
def save_attendance():
    data = request.json or {}
    attendance_date = data.get('date')
    selected_class = data.get('class')
    records = data.get('records', [])

    conn = get_db()
    cur = conn.cursor()
    for rec in records:
        cur.execute("""
            INSERT INTO attendance (date, class, student_name, status)
            VALUES (%s, %s, %s, %s)
        """, (attendance_date, selected_class, rec['name'], rec['status']))
    
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True, "message": "บันทึกการเช็คชื่อลง Neon เรียบร้อย!"})

@app.route('/dashboard')
def dashboard():
    if 'fullname' not in session:
        return redirect(url_for('login_page'))

    student_data = {
        "name": session['fullname'],
        "room": session.get('student_room', '-'),
        "next_class": {"subject": "อินเทอร์เน็ตในงานธุรกิจดิจิทัล", "time": "10:30 - 11:20", "room": "คอมฯ 1"},
        "today_schedule": [
            {"period": 1, "time": "08:30-09:20", "subject": "คณิตศาสตร์"},
            {"period": 2, "time": "09:20-10:10", "subject": "ภาษาอังกฤษ"}
        ],
        "assignments": []
    }
    return render_template('dashboard.html', data=student_data)

@app.route('/teacher_dashboard')
def teacher_dashboard():
    if session.get('role') != 'teacher':
        return redirect(url_for('login_page'))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT fullname, class FROM students ORDER BY class, fullname")
    students = cur.fetchall()
    
    classes = sorted(list(set(s['class'] for s in students)))
    all_students = [{"class": s['class'], "name": s['fullname']} for s in students]
    
    cur.close()
    conn.close()
    return render_template('teacher_dashboard.html', classes=classes, all_students=all_students)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)