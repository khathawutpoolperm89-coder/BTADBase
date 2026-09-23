"""LINE Login authorization-code flow and one-time student account binding."""
import os
import secrets
import time
from urllib.parse import urlencode

import psycopg2
import requests
from flask import redirect, render_template, request, session, url_for


def install_line_login(app, get_db):
    def configured():
        return all(os.environ.get(key) for key in (
            'SECRET_KEY', 'LINE_CHANNEL_ID', 'LINE_CHANNEL_SECRET', 'LINE_CALLBACK_URL'))

    app.jinja_env.globals['line_login_enabled'] = configured

    def page(message=None, status=200, binding=False):
        return render_template('line_link.html', message=message, binding=binding,
                               csrf=session.get('line_link_csrf', '')), status

    def sign_in(student):
        session.clear()
        session.update(role='student', fullname=student['fullname'],
                       student_id=student['student_id'], student_room=student['class'])
        return redirect(url_for('dashboard'))

    @app.route('/auth/line')
    def line_start():
        if not configured():
            return page('โรงเรียนยังไม่ได้เปิดใช้ LINE Login กรุณาเข้าสู่ระบบแบบเดิม', 503)
        session.clear()
        session['line_state'] = secrets.token_urlsafe(32)
        session['line_nonce'] = secrets.token_urlsafe(32)
        session['line_started'] = time.time()
        params = dict(response_type='code', client_id=os.environ['LINE_CHANNEL_ID'],
                      redirect_uri=os.environ['LINE_CALLBACK_URL'],
                      state=session['line_state'], nonce=session['line_nonce'], scope='openid')
        return redirect('https://access.line.me/oauth2/v2.1/authorize?' + urlencode(params))

    @app.route('/auth/line/callback')
    def line_callback():
        expected = session.pop('line_state', '')
        nonce = session.pop('line_nonce', '')
        started = session.pop('line_started', 0)
        state = request.args.get('state', '')
        if not expected or not secrets.compare_digest(expected, state) or time.time() - started > 600:
            return page('รายการเข้าสู่ระบบหมดอายุหรือไม่ถูกต้อง กรุณาเริ่มใหม่', 400)
        if request.args.get('error') or not request.args.get('code'):
            return page('ยังไม่ได้อนุญาตให้เข้าสู่ระบบด้วย LINE กรุณาลองใหม่', 400)
        try:
            token = requests.post('https://api.line.me/oauth2/v2.1/token', data={
                'grant_type': 'authorization_code', 'code': request.args['code'],
                'redirect_uri': os.environ['LINE_CALLBACK_URL'],
                'client_id': os.environ['LINE_CHANNEL_ID'],
                'client_secret': os.environ['LINE_CHANNEL_SECRET']}, timeout=15)
            token.raise_for_status()
            verification = requests.post('https://api.line.me/oauth2/v2.1/verify', data={
                'id_token': token.json()['id_token'], 'client_id': os.environ['LINE_CHANNEL_ID'],
                'nonce': nonce}, timeout=15)
            verification.raise_for_status()
            identity = verification.json()
            if not identity.get('sub') or identity.get('nonce') != nonce:
                return page('ยืนยันบัญชี LINE ไม่สำเร็จ กรุณาลองใหม่', 400)
            line_id = identity['sub']
        except (requests.RequestException, ValueError, KeyError):
            return page('เชื่อมต่อ LINE ไม่สำเร็จ กรุณาเริ่มใหม่', 502)
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT student_id, fullname, class FROM students WHERE line_user_id = %s', (line_id,))
                student = cur.fetchone()
        except psycopg2.Error:
            app.logger.error('LINE login database lookup failed')
            return page('ระบบผูกบัญชียังไม่พร้อม กรุณาติดต่อผู้ดูแลระบบ', 503)
        finally:
            conn.close()
        if student:
            return sign_in(student)
        session.clear()
        session.update(line_pending=line_id, line_link_started=time.time(),
                       line_link_csrf=secrets.token_urlsafe(32), line_link_attempts=0)
        return redirect(url_for('line_link'))

    @app.route('/auth/line/link', methods=['GET', 'POST'])
    def line_link():
        if not session.get('line_pending') or time.time()-session.get('line_link_started', 0)>600:
            return page('กรุณาเข้าสู่ระบบด้วย LINE อีกครั้งก่อนผูกบัญชี', 400)
        if request.method == 'GET':
            return page(binding=True)
        if not secrets.compare_digest(session.get('line_link_csrf', ''), request.form.get('csrf', '')):
            return page('คำขอไม่ถูกต้อง กรุณาเริ่มใหม่', 400)
        attempts = session.get('line_link_attempts', 0)
        if attempts >= 5:
            session.clear()
            return page('กรอกไม่สำเร็จหลายครั้ง กรุณาเข้าสู่ระบบ LINE ใหม่', 429)
        session['line_link_attempts'] = attempts + 1
        student_id = request.form.get('student_id', '').strip()
        if not student_id or len(student_id)>64:
            return page('กรุณากรอกเลขประจำตัวนักเรียนให้ถูกต้อง', 400, True)
        conn = get_db()
        try:
            with conn.cursor() as cur:
                # One conditional write prevents competing LINE accounts claiming the same student.
                cur.execute("""UPDATE students SET line_user_id = %s
                    WHERE student_id = %s AND line_user_id IS NULL
                    RETURNING student_id, fullname, class""", (session['line_pending'], student_id))
                student = cur.fetchone()
            if not student:
                conn.rollback()
                return page('ไม่พบเลขประจำตัวนี้ หรือถูกผูกกับ LINE แล้ว กรุณาติดต่ออาจารย์', 409, True)
            conn.commit()
        except psycopg2.IntegrityError:
            conn.rollback()
            return page('บัญชีนี้ถูกผูกแล้ว กรุณาเข้าสู่ระบบ LINE ใหม่', 409)
        except psycopg2.Error:
            conn.rollback()
            app.logger.error('LINE account binding database operation failed')
            return page('ผูกบัญชีไม่สำเร็จ กรุณาติดต่อผู้ดูแลระบบ', 503)
        finally:
            conn.close()
        return sign_in(student)
