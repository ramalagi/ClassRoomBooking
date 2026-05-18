from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, make_response
from models import (
    create_tables, insert_sample_data, backfill_course_master,
    backfill_attendance_v3, seed_default_letter_template,
    get_rooms, get_timeslots,
    get_bookings_for_date, make_booking, get_user, get_all_users,
    delete_user, cancel_booking, get_students, get_batches, get_attendance,
    mark_attendance as save_attendance, bulk_mark_attendance,
    get_student_attendance_history, get_attendance_summary,
    get_courses, get_years_for_course, get_sections_for_course_year,
    get_batch_by_course_year_section, add_batch, delete_batch,
    add_student, delete_student, get_students_with_batch,
    parse_students_xlsx,
    validate_student_rows, commit_validated_students,
    # Course Management master-data CRUD
    add_course, update_course, get_course_tree,
    add_course_year, delete_course_year, get_course_year, get_course,
    add_section, update_section, set_section_incharge,
    list_faculty,
    list_subjects, add_subject, update_subject,
    list_labs,     add_lab,     update_lab,
    parse_subjects_xlsx, bulk_add_subjects,
    parse_labs_xlsx,     bulk_add_labs,
    list_courses, list_course_years, list_sections,
    get_sections_for_staff, get_subjects_for_staff, get_labs_for_staff,
    set_user_sections, set_user_subjects, set_user_labs,
    find_or_create_batch_for_section,
    list_audit_log, list_audit_entities,
    get_user_incharge_sections,
    add_staff_with_temp_password, set_user_password, reset_user_password,
    # Attendance v3 service layer
    can_mark_attendance, can_mark_for_date, is_attendance_locked,
    is_section_incharge,
    get_attendance_settings,
    get_students_in_section, get_attendance_v3,
    get_my_sections, get_my_subjects, get_section_details,
    # Notifications (Day 4)
    enqueue_absent_notifications, claim_pending_notifications,
    mark_notification_sent, mark_notification_failed, retry_notification,
    list_notifications, update_attendance_settings,
    get_student_notify_prefs, set_student_notify_prefs,
    # Reports + archive (Day 5)
    report_section_summary, report_subject_summary,
    report_daily_absentees, report_faculty_activity,
    archive_old_attendance,
    # Absentee letters
    find_continuous_absentees, can_generate_absentee_letter,
    list_holidays, add_holiday, delete_holiday,
    compute_monthly_summary, get_letter_template, get_student_by_id,
    insert_absentee_letter_row, revoke_absentee_letter,
    list_absentee_letters,
    list_letter_templates, add_letter_template, update_letter_template,
)
from db import get_db_connection as _v2_db
import psycopg2
from datetime import datetime, timedelta

import os

app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates"
)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "please_change_this_secret"
)


def _send_email(to_address, subject, body):
    """Sends an email via SMTP if configured (SMTP_HOST + SMTP_USER + SMTP_PASSWORD
    env vars). Otherwise prints the message to the server console so the admin
    can see it in dev. Returns True on (apparent) successful send, False on
    failure or fallback."""
    if not to_address:
        print(f"[email] skipped: no recipient; subject={subject!r}")
        return False

    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    pwd  = os.getenv("SMTP_PASSWORD")
    port = int(os.getenv("SMTP_PORT", "587"))
    from_addr = os.getenv("SMTP_FROM", user or "no-reply@nttf.local")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

    print(
        "\n----- OUTGOING EMAIL --------------------------------------------\n"
        f"To: {to_address}\nFrom: {from_addr}\nSubject: {subject}\n\n"
        f"{body}\n"
        "------------------------------------------------------------------"
    )

    if not (host and user and pwd):
        print("[email] SMTP not configured (SMTP_HOST/SMTP_USER/SMTP_PASSWORD); "
              "logged above only.")
        return False

    import smtplib
    from email.mime.text import MIMEText
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_address
        with smtplib.SMTP(host, port, timeout=15) as srv:
            if use_tls:
                srv.starttls()
            srv.login(user, pwd)
            srv.sendmail(from_addr, [to_address], msg.as_string())
        return True
    except Exception as exc:
        print(f"[email] SMTP send failed: {exc}")
        return False


def _dispatch_notification(channel, recipient, body):
    """Returns (success: bool, provider_name: str, provider_msg_id: str|None,
    error: str|None, permanent: bool). Permanent=True means don't retry."""
    if channel == 'email':
        sent = _send_email(recipient, "Attendance notification", body)
        if sent:
            import uuid
            return True, 'smtp', 'smtp-' + uuid.uuid4().hex[:8], None, False
        # SMTP env not configured locally OR SMTP send failed.
        return False, 'smtp', None, 'SMTP not configured or send failed', False
    if channel == 'sms':
        # Stub — wire Twilio/MSG91/TextLocal here. Permanent until configured.
        return False, 'sms-stub', None, 'SMS provider not configured', True
    if channel == 'whatsapp':
        # Stub — wire Meta WhatsApp Cloud / Twilio WhatsApp here.
        return False, 'whatsapp-stub', None, 'WhatsApp provider not configured', True
    return False, None, None, f'Unknown channel: {channel}', True


_NOTIFY_WORKER_STARTED = False
def _start_notification_worker():
    """Spawns a daemon thread that polls ParentNotifications every 30s and
    dispatches queued rows via the channel's provider. Single instance per
    Flask process — multiple processes are safe due to FOR UPDATE SKIP LOCKED."""
    global _NOTIFY_WORKER_STARTED
    if _NOTIFY_WORKER_STARTED:
        return
    import threading, time
    def loop():
        # Small initial delay so the schema migrations finish before we start
        # claiming notifications.
        time.sleep(2)
        while True:
            try:
                batch = claim_pending_notifications(batch_size=25)
                for n in batch:
                    success, provider, msg_id, error, permanent = \
                        _dispatch_notification(n['channel'], n['recipient'],
                                              n['message_body'])
                    if success:
                        mark_notification_sent(n['id'], provider, msg_id)
                    else:
                        mark_notification_failed(n['id'], provider, error,
                                                permanent=permanent)
            except Exception as exc:
                # Never let the worker die — log and continue.
                print(f"[notify-worker] error: {exc}")
            time.sleep(30)
    t = threading.Thread(target=loop, daemon=True, name='notification-worker')
    t.start()
    _NOTIFY_WORKER_STARTED = True
    print("[notify-worker] started (30s tick)")


def _html_to_pdf_bytes(html_string):
    """Renders an HTML document to PDF bytes. Tries WeasyPrint first
    (better CSS fidelity on Linux), falls back to xhtml2pdf (pure-Python,
    Windows-friendly). Raises RuntimeError if neither is available."""
    try:
        from weasyprint import HTML
        return HTML(string=html_string).write_pdf()
    except Exception:
        pass
    try:
        from xhtml2pdf import pisa
        from io import BytesIO
        buf = BytesIO()
        result = pisa.CreatePDF(html_string, dest=buf, encoding='utf-8')
        if result.err:
            raise RuntimeError(f"xhtml2pdf reported {result.err} error(s)")
        return buf.getvalue()
    except ImportError as exc:
        raise RuntimeError(
            "No PDF renderer installed. Run `pip install xhtml2pdf` "
            "(Windows-friendly) or `pip install weasyprint` (Linux).") from exc


_LETTER_WRAPPER = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 22mm 18mm 18mm 18mm; }}
  body {{ font-family: 'Times New Roman', 'Liberation Serif', serif;
         font-size: 11pt; line-height: 1.5; color: #111; }}
  h2, h3, h4 {{ margin: 0.4em 0; }}
  p {{ margin: 0.55em 0; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ padding: 4pt 6pt; vertical-align: top; }}
  .footer-sigs td {{ text-align: center; padding-top: 48px;
                      font-size: .85rem; }}
</style></head>
<body>
{body}
</body></html>"""


def _render_letter_html(*, student, section, monthly_summary, letter_meta, template):
    """Renders the template's body_html with context, then wraps it in
    a print-friendly HTML doc. The template's HTML is admin-editable so
    we render via a sandboxed Jinja2 Environment, not Flask's renderer."""
    from jinja2 import Environment, BaseLoader, select_autoescape
    env = Environment(loader=BaseLoader(),
                      autoescape=select_autoescape(default=False))
    env.filters['nl2br'] = lambda v: (v or '').replace('\n', '<br>')

    today = datetime.now().date()
    body = env.from_string(template['body_html']).render(
        student={
            'id': student.id,
            'name': student.name,
            'student_code': student.student_code,
            'parent_name': student.parent_name,
            'parent_phone': student.parent_phone,
            'parent_email': student.parent_email,
            'phone': student.phone,
            'address': student.address,
            'email': student.email,
        },
        section=section,
        monthly_summary=monthly_summary,
        letter=letter_meta,
        template=template,
        today=today,
        today_str=today.strftime('%d/%m/%Y'),
        campus=os.getenv('CAMPUS_NAME', 'Dharwad'),
    )
    return _LETTER_WRAPPER.format(body=body)


def _onboarding_email_body(name, username, temp_password, login_url, is_reset=False):
    greeting = name or username
    intro = ("Your password has been reset by the administrator."
             if is_reset else
             "An account has been created for you on the NTTF Classroom Booking portal.")
    return (
        f"Hi {greeting},\n\n"
        f"{intro}\n\n"
        f"Login URL : {login_url}\n"
        f"Username  : {username}\n"
        f"Temporary password : {temp_password}\n\n"
        "After signing in, you'll be asked to set a new password before "
        "you can continue.\n\n"
        "If you didn't expect this email, please contact the administrator.\n\n"
        "— NTTF Admin"
    )


# Pick up template edits without restarting the server during development.
# Pick up template edits without restarting the server during development.
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True

@app.context_processor
def inject_nav_helpers():
    """Compute the right attendance link for the current user once per request."""
    role = session.get('role')
    user_id = session.get('user_id')
    if not user_id:
        return {}
    if role in ('admin', 'faculty'):
        return {'nav_attendance_url': url_for('attendance_dashboard')}
    if role == 'student':
        from models import get_students
        match = next((s for s in get_students() if s.user_id == user_id), None)
        if match:
            return {'nav_attendance_url': url_for('attendance_history', student_id=match.id)}
    return {'nav_attendance_url': url_for('dashboard')}


def login_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def admin_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Admin access required')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def faculty_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session or session.get('role') not in ['admin', 'faculty']:
            flash('Faculty access required')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def student_required(f):
    def wrapper(*args, **kwargs):
        if 'user_id' not in session or session.get('role') not in ['admin', 'faculty', 'student']:
            flash('Access required')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = get_user(username, password)
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[2]
            session['name'] = user[3]
            session['email'] = user[4]
            session['must_change_password'] = bool(user[5])
            if session['must_change_password']:
                flash('Welcome! Please set a new password before continuing.')
                return redirect(url_for('account_password'))
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials')
    return render_template('login.html')


@app.before_request
def _enforce_password_change():
    """If a user is logged in but flagged must_change_password, force them
    onto the password-change page until they've set a real password."""
    if 'user_id' not in session or not session.get('must_change_password'):
        return
    allowed = {'account_password', 'logout', 'login', 'static'}
    if request.endpoint in allowed:
        return
    return redirect(url_for('account_password'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/account/password', methods=['GET', 'POST'])
@login_required
def account_password():
    if request.method == 'POST':
        new_pw = request.form.get('new_password') or ''
        confirm = request.form.get('confirm_password') or ''
        if len(new_pw) < 8:
            flash('Password must be at least 8 characters.')
            return render_template('account_password.html', user=session)
        if new_pw != confirm:
            flash('Passwords do not match.')
            return render_template('account_password.html', user=session)
        if not any(c.isdigit() for c in new_pw) or not any(c.isalpha() for c in new_pw):
            flash('Use at least one letter and one digit.')
            return render_template('account_password.html', user=session)
        set_user_password(session['user_id'], new_pw, must_change=False)
        session['must_change_password'] = False
        flash('Password updated. You can now use the rest of the app.')
        return redirect(url_for('dashboard'))
    return render_template('account_password.html', user=session)

# Initialize database automatically if needed.
with app.app_context():
    create_tables()
    insert_sample_data()
    backfill_course_master()
    backfill_attendance_v3()
    seed_default_letter_template()
    _start_notification_worker()

@app.route('/')
@login_required
def dashboard():
    from models import get_students
    students = get_students()
    role = session.get('role')
    student_id = None
    if role == 'student':
        user_students = [s for s in students if s.user_id == session['user_id']]
        if user_students:
            student_id = user_students[0].id

    if role in ['admin', 'faculty']:
        attendance_url = url_for('attendance_dashboard')
        attendance_title = 'Attendance Management'
        attendance_description = 'Track student attendance, generate reports, and analyze performance with comprehensive analytics.'
    elif role == 'student' and student_id:
        attendance_url = url_for('attendance_history', student_id=student_id)
        attendance_title = 'My Attendance'
        attendance_description = 'View your attendance history, track your performance, and stay updated on your academic record.'
    else:
        attendance_url = url_for('attendance_dashboard')
        attendance_title = 'Attendance'
        attendance_description = 'Access attendance tools and reports for your role.'

    return render_template(
        'main_dashboard.html',
        student_id=student_id,
        attendance_url=attendance_url,
        attendance_title=attendance_title,
        attendance_description=attendance_description
    )

@app.route('/booking')
@login_required
def booking_dashboard():
    # Default to today's date
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    date = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    rooms = get_rooms()
    selected_day = date.strftime('%A')
    timeslots = [ts for ts in get_timeslots() if ts.day == selected_day]
    bookings = get_bookings_for_date(date)
    
    # Create a grid: room vs timeslot
    grid = {}
    now = datetime.now()
    today = now.date()
    for room in rooms:
        grid[room.id] = {}
        for ts in timeslots:
            start_hour = int(ts.period.split('-')[0].split(':')[0])
            if date < today or (date == today and now.hour >= start_hour):
                grid[room.id][ts.id] = {'status': 'unavailable', 'staff': None}
            else:
                grid[room.id][ts.id] = {'status': 'available', 'staff': None}
    
    for booking in bookings:
        booking_id, username, room_name, room_type, day, period, b_date, user_id = booking
        room_id = next((r.id for r in rooms if r.name == room_name), None)
        timeslot_id = next((ts.id for ts in timeslots if ts.day == day and ts.period == period), None)
        if room_id is None or timeslot_id is None or room_id not in grid or timeslot_id not in grid[room_id]:
            continue
        grid[room_id][timeslot_id] = {'status': 'busy', 'staff': username, 'booking_id': booking_id, 'user_id': user_id}
    
    today = datetime.now().date()
    selected_day = date.strftime('%A')
    role = session.get('role')
    student_id = None
    if role == 'student':
        from models import get_students
        students = get_students()
        user_students = [s for s in students if s.user_id == session['user_id']]
        if user_students:
            student_id = user_students[0].id
    return render_template('booking_dashboard.html', grid=grid, rooms=rooms, timeslots=timeslots, date=date_str, today=today, selected_day=selected_day, user=session, role=role, student_id=student_id)

@app.route('/book', methods=['GET', 'POST'])
@login_required
def book():
    if request.method == 'POST':
        user_id = session['user_id']
        try:
            room_id = int(request.form['room_id'])
            timeslot_id = int(request.form['timeslot_id'])
            date_str = request.form['date']
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (KeyError, ValueError):
            flash('Invalid booking request.')
            return redirect(url_for('booking_dashboard'))

        timeslot = next((ts for ts in get_timeslots() if ts.id == timeslot_id), None)
        if timeslot is None:
            flash('Selected time slot does not exist.')
            return redirect(url_for('booking_dashboard', date=date_str))

        start_hour = int(timeslot.period.split('-')[0].split(':')[0])
        now = datetime.now()
        today = now.date()

        if date < today:
            flash('Cannot book for past dates.')
            return redirect(url_for('booking_dashboard', date=date_str))
        if date == today and now.hour >= start_hour:
            flash('Cannot book for past or current time slots.')
            return redirect(url_for('booking_dashboard', date=date_str))
        if timeslot.day != date.strftime('%A'):
            flash(f'Selected timeslot day ({timeslot.day}) does not match the chosen date ({date.strftime("%A")}).')
            return redirect(url_for('booking_dashboard', date=date_str))

        if make_booking(user_id, room_id, timeslot_id, date):
            flash('Booking confirmed.')
            return redirect(url_for('booking_dashboard', date=date_str))
        flash('Booking failed: room already booked for that time.')
        return redirect(url_for('booking_dashboard', date=date_str))
    
    rooms = get_rooms()
    timeslots = get_timeslots()
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    date = datetime.strptime(date_str, '%Y-%m-%d').date()
    today = datetime.now().date()
    now_hour = datetime.now().hour
    selected_day = date.strftime('%A')
    
    # Filter timeslots for the selected day and to prevent past bookings
    if date < today:
        filtered_timeslots = []
    elif date == today:
        filtered_timeslots = [ts for ts in timeslots if ts.day == selected_day and int(ts.period.split('-')[0].split(':')[0]) > now_hour]
    else:
        filtered_timeslots = [ts for ts in timeslots if ts.day == selected_day]
    
    return render_template('book.html', rooms=rooms, timeslots=filtered_timeslots, date=date_str, today=today, selected_day=selected_day, user=session)

@app.route('/cancel/<int:booking_id>')
@login_required
def cancel(booking_id):
    user_id = session['user_id']
    is_admin = session.get('role') == 'admin'
    if cancel_booking(booking_id, user_id, is_admin):
        flash('Booking cancelled')
    else:
        flash('Cannot cancel this booking')
    return redirect(request.referrer or url_for('booking_dashboard'))

@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            username = (request.form.get('username') or '').strip()
            role = request.form.get('role') or ''
            name = (request.form.get('name') or '').strip() or None
            email = (request.form.get('email') or '').strip() or None
            if not (username and role):
                flash('Username and role are required.')
            elif role not in ('admin', 'faculty'):
                flash('Role must be admin or faculty.')
            elif not email:
                flash('Email is required so we can send the temporary password.')
            else:
                uid, temp_pw = add_staff_with_temp_password(
                    username, role, name=name, email=email,
                    actor_id=session['user_id']
                )
                if not uid:
                    flash('A user with that username already exists.')
                else:
                    login_url = request.host_url.rstrip('/') + url_for('login')
                    body = _onboarding_email_body(
                        name=name, username=username,
                        temp_password=temp_pw, login_url=login_url,
                    )
                    sent = _send_email(email, "NTTF Classroom Booking — your login", body)
                    if sent:
                        flash(f'User "{username}" added. Temporary password emailed to {email}.')
                    else:
                        flash(f'User "{username}" added. Email not sent (SMTP not configured). '
                              f'Temp password: {temp_pw}')
        elif action == 'delete':
            user_id = int(request.form['user_id'])
            delete_user(user_id)
            flash('User deleted')
    # Students are managed on the Students tab; the Users page is for staff
    # accounts only (admin + faculty).
    users = [u for u in get_all_users() if u[2] != 'student']
    incharge_map = get_user_incharge_sections()
    return render_template('admin.html', users=users,
                           incharge_map=incharge_map, user=session)


# ---- Admin: Batches --------------------------------------------------------

@app.route('/admin/batches', methods=['GET', 'POST'])
@admin_required
def admin_batches():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            course = (request.form.get('course') or '').strip()
            year = request.form.get('year')
            section = (request.form.get('section') or '').strip()
            name = (request.form.get('name') or '').strip() or f"{course} - Year {year} - {section}"
            try:
                year_int = int(year)
            except (TypeError, ValueError):
                flash('Year must be 1, 2 or 3.')
                return redirect(url_for('admin_batches'))
            if not (course and year_int and section):
                flash('Course, year and section are required.')
                return redirect(url_for('admin_batches'))
            try:
                add_batch(name, course, year_int, section)
                flash(f'Batch "{name}" added.')
            except Exception as exc:
                flash(f'Could not add batch: {exc}')
        elif action == 'delete':
            try:
                batch_id = int(request.form['batch_id'])
                delete_batch(batch_id)
                flash('Batch deleted.')
            except Exception as exc:
                flash(f'Could not delete batch: {exc}')
        return redirect(url_for('admin_batches'))
    batches = get_batches()
    return render_template('admin_batches.html', batches=batches, user=session)


# ---- Admin: Course Management (Courses → Years → Sections) -----------------

@app.route('/admin/courses')
@admin_required
def admin_courses():
    tree = get_course_tree()
    faculty = list_faculty()
    return render_template('admin_courses.html', tree=tree, faculty=faculty,
                           user=session)


@app.route('/admin/courses/add', methods=['POST'])
@admin_required
def admin_add_course():
    try:
        code = (request.form.get('code') or '').strip().upper()
        name = (request.form.get('name') or '').strip()
        if not (code and name):
            flash('Code and name are required.')
            return redirect(url_for('admin_courses'))
        add_course(code, name, actor_id=session['user_id'])
        flash(f'Course "{name}" added.')
    except psycopg2.errors.UniqueViolation:
        flash(f'Course code already exists. Pick a different code.')
    except Exception as exc:
        flash(f'Could not add course: {exc}')
    return redirect(url_for('admin_courses'))


@app.route('/admin/courses/<int:course_id>/deactivate', methods=['POST'])
@admin_required
def admin_deactivate_course(course_id):
    try:
        update_course(course_id, is_active=False, actor_id=session['user_id'])
        flash('Course deactivated.')
    except Exception as exc:
        flash(f'Could not deactivate course: {exc}')
    return redirect(url_for('admin_courses'))


@app.route('/admin/courses/<int:course_id>/reactivate', methods=['POST'])
@admin_required
def admin_reactivate_course(course_id):
    try:
        update_course(course_id, is_active=True, actor_id=session['user_id'])
        flash('Course reactivated.')
    except Exception as exc:
        flash(f'Could not reactivate course: {exc}')
    return redirect(url_for('admin_courses'))


@app.route('/admin/courses/<int:course_id>/years/add', methods=['POST'])
@admin_required
def admin_add_course_year(course_id):
    try:
        year_number = int(request.form.get('year_number'))
        add_course_year(course_id, year_number, actor_id=session['user_id'])
        flash(f'Year {year_number} added.')
    except psycopg2.errors.UniqueViolation:
        flash('That year already exists for this course.')
    except (TypeError, ValueError):
        flash('Year must be between 1 and 6.')
    except Exception as exc:
        flash(f'Could not add year: {exc}')
    return redirect(url_for('admin_courses'))


@app.route('/admin/course-years/<int:course_year_id>/delete', methods=['POST'])
@admin_required
def admin_delete_course_year(course_year_id):
    try:
        delete_course_year(course_year_id, actor_id=session['user_id'])
        flash('Year removed.')
    except psycopg2.errors.ForeignKeyViolation:
        flash('Cannot remove a year that still has sections. Deactivate or remove its sections first.')
    except Exception as exc:
        flash(f'Could not remove year: {exc}')
    return redirect(url_for('admin_courses'))


@app.route('/admin/course-years/<int:course_year_id>/sections/add', methods=['POST'])
@admin_required
def admin_add_section(course_year_id):
    try:
        section_code = (request.form.get('section_code') or '').strip().upper()
        if not section_code:
            flash('Section code is required.')
            return redirect(url_for('admin_courses'))
        add_section(course_year_id, section_code, actor_id=session['user_id'])
        flash(f'Section {section_code} added.')
    except psycopg2.errors.UniqueViolation:
        flash('That section already exists for this course-year.')
    except Exception as exc:
        flash(f'Could not add section: {exc}')
    return redirect(url_for('admin_courses'))


@app.route('/admin/sections/<int:section_id>/deactivate', methods=['POST'])
@admin_required
def admin_deactivate_section(section_id):
    try:
        update_section(section_id, is_active=False, actor_id=session['user_id'])
        flash('Section deactivated.')
    except Exception as exc:
        flash(f'Could not deactivate section: {exc}')
    return redirect(url_for('admin_courses'))


@app.route('/admin/sections/<int:section_id>/reactivate', methods=['POST'])
@admin_required
def admin_reactivate_section(section_id):
    try:
        update_section(section_id, is_active=True, actor_id=session['user_id'])
        flash('Section reactivated.')
    except Exception as exc:
        flash(f'Could not reactivate section: {exc}')
    return redirect(url_for('admin_courses'))


@app.route('/admin/course-years/<int:course_year_id>')
@admin_required
def admin_course_year_detail(course_year_id):
    cy = get_course_year(course_year_id)
    if not cy:
        flash('Course-year not found.')
        return redirect(url_for('admin_courses'))
    course = get_course(cy.course_id)
    subjects = list_subjects(course_year_id)
    labs = list_labs(course_year_id)
    return render_template('admin_course_year.html',
                           course=course, course_year=cy,
                           subjects=subjects, labs=labs, user=session)


@app.route('/admin/course-years/<int:course_year_id>/subjects/add', methods=['POST'])
@admin_required
def admin_add_subject(course_year_id):
    try:
        code = (request.form.get('code') or '').strip().upper()
        name = (request.form.get('name') or '').strip()
        credits_raw = (request.form.get('credits') or '').strip()
        credits = int(credits_raw) if credits_raw else None
        if not (code and name):
            flash('Subject code and name are required.')
            return redirect(url_for('admin_course_year_detail', course_year_id=course_year_id))
        add_subject(course_year_id, code, name, credits=credits,
                    actor_id=session['user_id'])
        flash(f'Subject "{name}" added.')
    except psycopg2.errors.UniqueViolation:
        flash('A subject with that code already exists for this course-year.')
    except Exception as exc:
        flash(f'Could not add subject: {exc}')
    return redirect(url_for('admin_course_year_detail', course_year_id=course_year_id))


@app.route('/admin/course-years/<int:course_year_id>/subjects/upload', methods=['POST'])
@admin_required
def admin_upload_subjects(course_year_id):
    upload = request.files.get('file')
    if not upload or not upload.filename:
        flash('Please choose an Excel (.xlsx) file to upload.')
        return redirect(url_for('admin_course_year_detail', course_year_id=course_year_id))
    if not upload.filename.lower().endswith('.xlsx'):
        flash('Only .xlsx files are supported.')
        return redirect(url_for('admin_course_year_detail', course_year_id=course_year_id))
    try:
        records = parse_subjects_xlsx(upload.stream)
    except ValueError as exc:
        flash(f'Upload failed: {exc}')
        return redirect(url_for('admin_course_year_detail', course_year_id=course_year_id))
    added, skipped, errors = bulk_add_subjects(course_year_id, records,
                                               actor_id=session['user_id'])
    summary = f'Added {added} subject(s).'
    if skipped:
        summary += f' Skipped {skipped} duplicate code(s).'
    if errors:
        summary += f' {len(errors)} error(s): ' + '; '.join(errors[:3])
    flash(summary)
    return redirect(url_for('admin_course_year_detail', course_year_id=course_year_id))


@app.route('/admin/subjects/<int:subject_id>/deactivate', methods=['POST'])
@admin_required
def admin_deactivate_subject(subject_id):
    cy_id = request.form.get('course_year_id', type=int)
    update_subject(subject_id, is_active=False, actor_id=session['user_id'])
    flash('Subject deactivated.')
    return redirect(url_for('admin_course_year_detail', course_year_id=cy_id))


@app.route('/admin/subjects/<int:subject_id>/reactivate', methods=['POST'])
@admin_required
def admin_reactivate_subject(subject_id):
    cy_id = request.form.get('course_year_id', type=int)
    update_subject(subject_id, is_active=True, actor_id=session['user_id'])
    flash('Subject reactivated.')
    return redirect(url_for('admin_course_year_detail', course_year_id=cy_id))


@app.route('/admin/course-years/<int:course_year_id>/labs/add', methods=['POST'])
@admin_required
def admin_add_lab(course_year_id):
    try:
        code = (request.form.get('code') or '').strip().upper()
        name = (request.form.get('name') or '').strip()
        if not (code and name):
            flash('Lab code and name are required.')
            return redirect(url_for('admin_course_year_detail', course_year_id=course_year_id))
        add_lab(course_year_id, code, name, actor_id=session['user_id'])
        flash(f'Lab "{name}" added.')
    except psycopg2.errors.UniqueViolation:
        flash('A lab with that code already exists for this course-year.')
    except Exception as exc:
        flash(f'Could not add lab: {exc}')
    return redirect(url_for('admin_course_year_detail', course_year_id=course_year_id))


@app.route('/admin/course-years/<int:course_year_id>/labs/upload', methods=['POST'])
@admin_required
def admin_upload_labs(course_year_id):
    upload = request.files.get('file')
    if not upload or not upload.filename:
        flash('Please choose an Excel (.xlsx) file to upload.')
        return redirect(url_for('admin_course_year_detail', course_year_id=course_year_id))
    if not upload.filename.lower().endswith('.xlsx'):
        flash('Only .xlsx files are supported.')
        return redirect(url_for('admin_course_year_detail', course_year_id=course_year_id))
    try:
        records = parse_labs_xlsx(upload.stream)
    except ValueError as exc:
        flash(f'Upload failed: {exc}')
        return redirect(url_for('admin_course_year_detail', course_year_id=course_year_id))
    added, skipped, errors = bulk_add_labs(course_year_id, records,
                                           actor_id=session['user_id'])
    summary = f'Added {added} lab(s).'
    if skipped:
        summary += f' Skipped {skipped} duplicate code(s).'
    if errors:
        summary += f' {len(errors)} error(s): ' + '; '.join(errors[:3])
    flash(summary)
    return redirect(url_for('admin_course_year_detail', course_year_id=course_year_id))


@app.route('/admin/labs/<int:lab_id>/deactivate', methods=['POST'])
@admin_required
def admin_deactivate_lab(lab_id):
    cy_id = request.form.get('course_year_id', type=int)
    update_lab(lab_id, is_active=False, actor_id=session['user_id'])
    flash('Lab deactivated.')
    return redirect(url_for('admin_course_year_detail', course_year_id=cy_id))


@app.route('/admin/labs/<int:lab_id>/reactivate', methods=['POST'])
@admin_required
def admin_reactivate_lab(lab_id):
    cy_id = request.form.get('course_year_id', type=int)
    update_lab(lab_id, is_active=True, actor_id=session['user_id'])
    flash('Lab reactivated.')
    return redirect(url_for('admin_course_year_detail', course_year_id=cy_id))


@app.route('/admin/sections/<int:section_id>/incharge', methods=['POST'])
@admin_required
def admin_set_section_incharge(section_id):
    try:
        raw = (request.form.get('user_id') or '').strip()
        user_id = int(raw) if raw else None
        set_section_incharge(section_id, user_id, actor_id=session['user_id'])
        flash('Section incharge cleared.' if user_id is None else 'Section incharge updated.')
    except Exception as exc:
        flash(f'Could not update incharge: {exc}')
    return redirect(url_for('admin_courses'))


# ---- Admin: Audit log viewer ----------------------------------------------

@app.route('/api/v3/students/<int:student_id>/notify-prefs', methods=['GET', 'PUT'])
@admin_required
def api_v3_student_notify_prefs(student_id):
    if request.method == 'GET':
        prefs = get_student_notify_prefs(student_id)
        if not prefs:
            return jsonify({'error': 'student not found'}), 404
        return jsonify(prefs)
    # PUT
    payload = request.get_json(silent=True) or {}
    # notify_channels: None = inherit; [] = opt out; ['sms', ...] = explicit
    nc = payload.get('notify_channels', '__unset__')
    if nc != '__unset__':
        if nc is None or isinstance(nc, list):
            # validate channel names
            if isinstance(nc, list):
                nc = [c for c in nc if c in ('sms', 'whatsapp', 'email')]
        else:
            return jsonify({'error': 'notify_channels must be null or list'}), 400
    parent_phone = payload.get('parent_phone')
    parent_email = payload.get('parent_email')
    ok = set_student_notify_prefs(
        student_id,
        parent_phone=parent_phone,
        parent_email=parent_email,
        notify_channels=nc,
        actor_id=session['user_id'],
    )
    if not ok:
        return jsonify({'error': 'student not found'}), 404
    return jsonify(get_student_notify_prefs(student_id))


@app.route('/admin/attendance/settings', methods=['GET', 'POST'])
@admin_required
def admin_attendance_settings():
    if request.method == 'POST':
        try:
            channels = request.form.getlist('notify_channels')
            update_attendance_settings(
                edit_window_hours=request.form.get('edit_window_hours', type=int),
                allow_backdate_days=request.form.get('allow_backdate_days', type=int),
                notify_absent=(request.form.get('notify_absent') == 'on'),
                notify_channels=channels,
                message_template=(request.form.get('message_template') or '').strip(),
                actor_id=session['user_id'],
            )
            flash('Attendance settings updated.')
        except Exception as exc:
            flash(f'Could not save settings: {exc}')
        return redirect(url_for('admin_attendance_settings'))
    settings = get_attendance_settings()
    return render_template('admin_attendance_settings.html',
                           settings=settings, user=session)


@app.route('/admin/notifications')
@admin_required
def admin_notifications():
    status = (request.args.get('status') or '').strip() or None
    student_id = request.args.get('student_id', type=int)
    try:
        limit = max(1, min(int(request.args.get('limit', 200)), 1000))
    except ValueError:
        limit = 200
    rows = list_notifications(status=status, student_id=student_id, limit=limit)
    # Compute counts per status for the filter chips
    counts = {'queued': 0, 'sending': 0, 'sent': 0, 'failed': 0, 'suppressed': 0}
    for r in list_notifications(limit=1000):
        counts[r['status']] = counts.get(r['status'], 0) + 1
    return render_template('admin_notifications.html',
                           rows=rows, counts=counts,
                           filter_status=status, filter_limit=limit,
                           user=session)


@app.route('/admin/letters')
@admin_required
def admin_letters():
    section_id = request.args.get('section_id', type=int)
    student_id = request.args.get('student_id', type=int)
    show_revoked = request.args.get('show_revoked', '').lower() in ('1', 'true', 'yes')
    try:
        limit = max(1, min(int(request.args.get('limit', 100)), 1000))
    except ValueError:
        limit = 100
    rows = list_absentee_letters(
        section_id=section_id, student_id=student_id,
        include_revoked=show_revoked, limit=limit,
    )
    sections = get_my_sections(session['user_id'], role=session.get('role'))
    return render_template('admin_letters.html',
                           rows=rows, sections=sections,
                           filter_section_id=section_id,
                           show_revoked=show_revoked,
                           user=session)


@app.route('/admin/letter-templates')
@admin_required
def admin_letter_templates():
    templates = list_letter_templates()
    return render_template('admin_letter_templates.html',
                           templates=templates, user=session)


@app.route('/admin/letter-templates/new', methods=['GET', 'POST'])
@admin_required
def admin_letter_template_new():
    if request.method == 'POST':
        try:
            name = (request.form.get('name') or '').strip()
            subject_line = (request.form.get('subject_line') or '').strip()
            body_html = request.form.get('body_html') or ''
            signature_blocks = [s.strip() for s in
                                (request.form.get('signature_blocks') or '').split('|')
                                if s.strip()]
            if not (name and subject_line and body_html):
                flash('Name, subject line and body HTML are required.')
                return redirect(url_for('admin_letter_template_new'))
            tid = add_letter_template(
                name, subject_line, body_html,
                signature_blocks=signature_blocks or None,
                actor_id=session['user_id'],
            )
            flash(f'Template "{name}" created.')
            return redirect(url_for('admin_letter_template_edit', template_id=tid))
        except Exception as exc:
            flash(f'Could not create template: {exc}')
            return redirect(url_for('admin_letter_template_new'))
    return render_template('admin_letter_template_edit.html',
                           template=None, user=session)


@app.route('/admin/letter-templates/<int:template_id>', methods=['GET', 'POST'])
@admin_required
def admin_letter_template_edit(template_id):
    tpl = get_letter_template(template_id)
    if not tpl:
        flash('Template not found.')
        return redirect(url_for('admin_letter_templates'))
    if request.method == 'POST':
        action = request.form.get('action') or 'save'
        try:
            if action == 'save':
                signature_blocks = [s.strip() for s in
                                    (request.form.get('signature_blocks') or '').split('|')
                                    if s.strip()]
                update_letter_template(
                    template_id,
                    name=(request.form.get('name') or '').strip() or None,
                    subject_line=(request.form.get('subject_line') or '').strip() or None,
                    body_html=request.form.get('body_html'),
                    signature_blocks=signature_blocks or None,
                    is_active=(request.form.get('is_active') == 'on'),
                    is_default=(request.form.get('is_default') == 'on'),
                    actor_id=session['user_id'],
                )
                flash('Template saved.')
            elif action == 'make_default':
                update_letter_template(template_id, is_default=True,
                                       actor_id=session['user_id'])
                flash('Template set as default.')
        except Exception as exc:
            flash(f'Could not save: {exc}')
        return redirect(url_for('admin_letter_template_edit', template_id=template_id))
    return render_template('admin_letter_template_edit.html',
                           template=tpl, user=session)


@app.route('/admin/letter-templates/<int:template_id>/preview')
@admin_required
def admin_letter_template_preview(template_id):
    """Renders the template body with synthetic sample data — useful while
    editing. Streams a PDF for download."""
    tpl = get_letter_template(template_id)
    if not tpl:
        return jsonify({'error': 'not_found'}), 404
    # Synthetic student + monthly summary
    from collections import namedtuple as _nt
    SampleStudent = _nt('SampleStudent', ['id', 'name', 'student_code',
        'parent_name', 'parent_phone', 'parent_email', 'phone', 'address',
        'email', 'section_id'])
    student = SampleStudent(
        id=0, name='Sample Student', student_code='S0001',
        parent_name='Sample Parent', parent_phone='9999912345',
        parent_email='parent@example.com', phone='9999900001',
        address='12 Sample Lane, Sample City 560001',
        email='student@example.com', section_id=0,
    )
    section = {'id': 0, 'full_code': 'M1A', 'section_code': 'A',
               'course_name': 'Mechatronics', 'year_number': 1, 'is_active': True}
    monthly = [
        {'month': 'JANUARY',  'absent_days': 8, 'class_days': 24, 'month_pct': 33.33, 'cumulative_pct': 33.33},
        {'month': 'FEBRUARY', 'absent_days': 5, 'class_days': 20, 'month_pct': 25.00, 'cumulative_pct': 29.55},
    ]
    from datetime import date as _d
    letter_meta = {
        'ref': '792',
        'consecutive_days': 8,
        'absent_from': _d.today(), 'absent_to': _d.today(),
        'absent_from_str': '01/02/2026', 'absent_to_str': '08/02/2026',
    }
    try:
        html = _render_letter_html(student=student, section=section,
                                    monthly_summary=monthly,
                                    letter_meta=letter_meta, template=tpl)
        pdf_bytes = _html_to_pdf_bytes(html)
    except Exception as exc:
        return f"<pre>Preview render failed: {exc}</pre>", 500
    resp = make_response(pdf_bytes)
    resp.headers['Content-Type'] = 'application/pdf'
    resp.headers['Content-Disposition'] = f'inline; filename=preview_{template_id}.pdf'
    return resp


@app.route('/admin/holidays', methods=['GET', 'POST'])
@admin_required
def admin_holidays():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            date_str = (request.form.get('date') or '').strip()
            name = (request.form.get('name') or '').strip()
            notes = (request.form.get('notes') or '').strip() or None
            if not (date_str and name):
                flash('Date and name are required.')
            else:
                try:
                    target = datetime.strptime(date_str, '%Y-%m-%d').date()
                    add_holiday(target, name, notes=notes,
                                actor_id=session['user_id'])
                    flash(f'Added holiday: {target} — {name}.')
                except psycopg2.errors.UniqueViolation:
                    flash('A holiday already exists on that date.')
                except Exception as exc:
                    flash(f'Could not add holiday: {exc}')
        elif action == 'delete':
            try:
                hid = int(request.form['holiday_id'])
                if delete_holiday(hid, actor_id=session['user_id']):
                    flash('Holiday removed.')
                else:
                    flash('Holiday not found.')
            except Exception as exc:
                flash(f'Could not remove holiday: {exc}')
        return redirect(url_for('admin_holidays'))

    from datetime import date as _d
    year = request.args.get('year', type=int) or _d.today().year
    holidays = list_holidays(_d(year, 1, 1), _d(year, 12, 31))
    return render_template('admin_holidays.html',
                           holidays=holidays, year=year, user=session)


@app.route('/admin/letters/<int:letter_id>/revoke', methods=['POST'])
@admin_required
def admin_letter_revoke(letter_id):
    reason = (request.form.get('reason') or '').strip() or None
    if revoke_absentee_letter(letter_id, session['user_id'], reason=reason):
        flash('Letter revoked.')
    else:
        flash('Letter is already revoked or could not be found.')
    return redirect(request.referrer or url_for('admin_letters'))


@app.route('/admin/notifications/<int:notif_id>/retry', methods=['POST'])
@admin_required
def admin_retry_notification(notif_id):
    if retry_notification(notif_id):
        flash('Notification re-queued.')
    else:
        flash('Notification cannot be retried (only failed/suppressed rows can be).')
    return redirect(request.referrer or url_for('admin_notifications'))


@app.route('/admin/audit')
@admin_required
def admin_audit():
    entity    = (request.args.get('entity') or '').strip() or None
    entity_id = request.args.get('entity_id', type=int)
    action    = (request.args.get('action') or '').strip() or None
    try:
        limit = max(1, min(int(request.args.get('limit', 200)), 1000))
    except ValueError:
        limit = 200
    entries = list_audit_log(entity=entity, entity_id=entity_id,
                             action=action, limit=limit)
    entities = list_audit_entities()
    return render_template('admin_audit.html',
                           entries=entries, entities=entities,
                           filter_entity=entity, filter_entity_id=entity_id,
                           filter_action=action, filter_limit=limit,
                           user=session)


@app.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def admin_reset_password(user_id):
    try:
        result = reset_user_password(user_id, actor_id=session['user_id'])
        if not result:
            flash('User not found.')
            return redirect(url_for('admin'))
        username, email, temp_pw = result
        if email:
            login_url = request.host_url.rstrip('/') + url_for('login')
            body = _onboarding_email_body(
                name=None, username=username,
                temp_password=temp_pw, login_url=login_url, is_reset=True,
            )
            sent = _send_email(email, "NTTF Classroom Booking — password reset", body)
        else:
            sent = False
        if sent:
            flash(f'Password reset for "{username}". New temp password sent to {email}.')
        else:
            flash(f'Password reset for "{username}". Email not sent — '
                  f'temp password: {temp_pw}')
    except Exception as exc:
        flash(f'Could not reset password: {exc}')
    return redirect(url_for('admin'))


# ---- Admin: Staff mappings (per user) -------------------------------------

def _user_summary(user_id):
    """Returns (id, username, role, name, email) for the user, or None."""
    return next((u for u in get_all_users() if u[0] == user_id), None)


def _tree_with_assignments(user_id):
    """Tree of courses → years → sections, with each section pre-flagged
    'is_assigned' / 'is_incharge' for this user. Used to render the picker."""
    tree = get_course_tree(active_only=True)
    my_sections = {s[0]: s[2] for s in get_sections_for_staff(user_id)}  # id -> incharge
    for course in tree:
        for year in course['years']:
            for sec in year['sections']:
                sec['is_assigned'] = sec['id'] in my_sections
                sec['is_incharge'] = my_sections.get(sec['id'], False)
    return tree


def _parse_assignments(form, id_field):
    """Pulls a destructive-replace assignment list out of a multi-checkbox
    form. id_field is e.g. 'section_id' / 'subject_id' / 'lab_id'."""
    selected = request.form.getlist(id_field, type=int)
    incharge_prefix = 'incharge_'
    incharge_ids = {
        int(k[len(incharge_prefix):]) for k in form.keys()
        if k.startswith(incharge_prefix) and k[len(incharge_prefix):].isdigit()
    }
    return [{id_field: i, 'is_incharge': i in incharge_ids} for i in selected]


@app.route('/admin/users/<int:user_id>/mappings')
@admin_required
def admin_user_mappings(user_id):
    user_row = _user_summary(user_id)
    if not user_row:
        flash('User not found.')
        return redirect(url_for('admin'))
    if user_row[2] not in ('faculty', 'admin'):
        flash('Only faculty and admin users can be assigned to sections/subjects/labs.')
        return redirect(url_for('admin'))

    section_tree = _tree_with_assignments(user_id)

    # Subjects & Labs: build a flat per-course-year listing with assignment flags
    my_subjects = {s[0]: s[3] for s in get_subjects_for_staff(user_id)}
    my_labs = {l[0]: l[3] for l in get_labs_for_staff(user_id)}
    subject_groups, lab_groups = [], []
    for course in list_courses(active_only=True):
        for cy in list_course_years(course.id):
            subs = list_subjects(cy.id, active_only=True)
            labs = list_labs(cy.id, active_only=True)
            if not subs and not labs:
                continue
            label = f"{course.code} — Year {cy.year_number}"
            if subs:
                subject_groups.append({
                    'label': label,
                    'items': [{
                        'id': s.id, 'code': s.code, 'name': s.name,
                        'is_assigned': s.id in my_subjects,
                        'is_incharge': my_subjects.get(s.id, False),
                    } for s in subs],
                })
            if labs:
                lab_groups.append({
                    'label': label,
                    'items': [{
                        'id': l.id, 'code': l.code, 'name': l.name,
                        'is_assigned': l.id in my_labs,
                        'is_incharge': my_labs.get(l.id, False),
                    } for l in labs],
                })

    return render_template(
        'admin_user_mappings.html',
        target_user=user_row, section_tree=section_tree,
        subject_groups=subject_groups, lab_groups=lab_groups,
        user=session,
    )


@app.route('/admin/users/<int:user_id>/mappings/sections', methods=['POST'])
@admin_required
def admin_save_user_sections(user_id):
    try:
        assignments = _parse_assignments(request.form, 'section_id')
        set_user_sections(user_id, assignments, actor_id=session['user_id'])
        flash(f'Section assignments saved ({len(assignments)} section(s)).')
    except Exception as exc:
        flash(f'Could not save sections: {exc}')
    return redirect(url_for('admin_user_mappings', user_id=user_id))


@app.route('/admin/users/<int:user_id>/mappings/subjects', methods=['POST'])
@admin_required
def admin_save_user_subjects(user_id):
    try:
        assignments = _parse_assignments(request.form, 'subject_id')
        set_user_subjects(user_id, assignments, actor_id=session['user_id'])
        flash(f'Subject assignments saved ({len(assignments)} subject(s)).')
    except Exception as exc:
        flash(f'Could not save subjects: {exc}')
    return redirect(url_for('admin_user_mappings', user_id=user_id))


@app.route('/admin/users/<int:user_id>/mappings/labs', methods=['POST'])
@admin_required
def admin_save_user_labs(user_id):
    try:
        assignments = _parse_assignments(request.form, 'lab_id')
        set_user_labs(user_id, assignments, actor_id=session['user_id'])
        flash(f'Lab assignments saved ({len(assignments)} lab(s)).')
    except Exception as exc:
        flash(f'Could not save labs: {exc}')
    return redirect(url_for('admin_user_mappings', user_id=user_id))


# ---- Admin: Students -------------------------------------------------------

@app.route('/admin/students', methods=['GET'])
@admin_required
def admin_students():
    students = get_students_with_batch()
    courses = list_courses(active_only=True)
    return render_template('admin_students.html',
                           students=students, courses=courses,
                           user=session)


@app.route('/admin/students/add', methods=['POST'])
@admin_required
def admin_add_student():
    try:
        name = (request.form.get('name') or '').strip()
        student_code = (request.form.get('student_code') or '').strip()
        email = (request.form.get('email') or '').strip() or None
        parent_name = (request.form.get('parent_name') or '').strip() or None
        phone = (request.form.get('phone') or '').strip() or None
        address = (request.form.get('address') or '').strip() or None
        section_raw = (request.form.get('section_id') or '').strip()
        section_id = int(section_raw) if section_raw else None
        if not (name and student_code):
            flash('Student ID and full name are required.')
            return redirect(url_for('admin_students'))
        add_student(name=name, email=email, student_code=student_code,
                    parent_name=parent_name, phone=phone, address=address,
                    section_id=section_id, actor_id=session['user_id'])
        if section_id:
            flash(f'Student "{name}" added.')
        else:
            flash(f'Student "{name}" added as unassigned. Edit later to set a section.')
    except psycopg2.errors.UniqueViolation:
        flash('A student with that ID already exists.')
    except Exception as exc:
        flash(f'Could not add student: {exc}')
    return redirect(url_for('admin_students'))


@app.route('/admin/students/upload', methods=['POST'])
@admin_required
def admin_upload_students():
    """Step 1: parse + validate. Renders a preview page; commit happens via
    a separate POST so admins see verdicts before any DB writes."""
    upload = request.files.get('file')
    if not upload or not upload.filename:
        flash('Please choose an Excel (.xlsx) file to upload.')
        return redirect(url_for('admin_students'))
    if not upload.filename.lower().endswith('.xlsx'):
        flash('Only .xlsx files are supported.')
        return redirect(url_for('admin_students'))
    try:
        records = parse_students_xlsx(upload.stream)
    except ValueError as exc:
        flash(f'Upload failed: {exc}')
        return redirect(url_for('admin_students'))
    except Exception as exc:
        flash(f'Could not read the Excel file: {exc}')
        return redirect(url_for('admin_students'))

    preview = validate_student_rows(records)
    import json as _json
    rows_json = _json.dumps(preview['rows'])
    return render_template('admin_students_upload_preview.html',
                           rows=preview['rows'], summary=preview['summary'],
                           rows_json=rows_json, filename=upload.filename,
                           user=session)


@app.route('/admin/students/upload/commit', methods=['POST'])
@admin_required
def admin_commit_students():
    """Step 2: insert the validated rows. Re-validates server-side against
    current master tables; tampered section_ids are ignored."""
    import json as _json
    raw = request.form.get('rows_json') or '[]'
    try:
        rows = _json.loads(raw)
    except _json.JSONDecodeError:
        flash('Upload session expired or corrupted. Please re-upload the file.')
        return redirect(url_for('admin_students'))
    if not isinstance(rows, list):
        flash('Invalid commit payload.')
        return redirect(url_for('admin_students'))
    inserted, skipped, errors = commit_validated_students(rows,
                                                          actor_id=session['user_id'])
    summary = f'Imported {inserted} student(s).'
    if skipped:
        summary += f' Skipped {skipped} invalid/duplicate row(s).'
    if errors:
        summary += f' {len(errors)} insert error(s): ' + '; '.join(errors[:3])
        if len(errors) > 3:
            summary += f' (+{len(errors) - 3} more)'
    flash(summary)
    return redirect(url_for('admin_students'))


@app.route('/admin/students/<int:student_id>/delete', methods=['POST'])
@admin_required
def admin_delete_student(student_id):
    try:
        if delete_student(student_id):
            flash('Student removed.')
        else:
            flash('Student not found.')
    except Exception as exc:
        flash(f'Could not delete student: {exc}')
    return redirect(url_for('admin_students'))


@app.route('/admin/students/sample.xlsx')
@admin_required
def admin_students_sample():
    """Download a sample .xlsx with the expected columns and one example row."""
    from openpyxl import Workbook
    from io import BytesIO
    wb = Workbook()
    ws = wb.active
    ws.title = 'Students'
    ws.append(['student_code', 'name', 'email', 'course', 'year', 'section',
               'parent_name', 'phone', 'address'])
    ws.append(['S101', 'Jane Doe', 'jane@nttf.com', 'Computer Science', 1, 'A',
               'John Doe', '9876543210', '#42, MG Road, Bengaluru 560001'])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = make_response(buf.read())
    response.headers['Content-Disposition'] = 'attachment; filename=students_sample.xlsx'
    response.headers['Content-Type'] = (
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    return response


# ---- Cascade API: Course -> Year -> Section -> Batch ----------------------

def _faculty_filter():
    """Return the faculty id to filter by, or None for admins."""
    if session.get('role') == 'faculty':
        return session.get('user_id')
    return None


@app.route('/api/courses')
@login_required
def api_courses():
    return jsonify(get_courses(_faculty_filter()))


@app.route('/api/years')
@login_required
def api_years():
    course = request.args.get('course')
    if not course:
        return jsonify([])
    return jsonify(get_years_for_course(course, _faculty_filter()))


@app.route('/api/sections')
@login_required
def api_sections():
    course = request.args.get('course')
    year = request.args.get('year', type=int)
    if not (course and year):
        return jsonify([])
    return jsonify(get_sections_for_course_year(course, year, _faculty_filter()))


@app.route('/api/batch')
@login_required
def api_batch():
    course = request.args.get('course')
    year = request.args.get('year', type=int)
    section = request.args.get('section')
    if not (course and year and section):
        return jsonify({'batch_id': None})
    batch = get_batch_by_course_year_section(course, year, section, _faculty_filter())
    return jsonify({
        'batch_id': batch.id if batch else None,
        'batch_name': batch.name if batch else None,
    })


# ---- Cascade API v2 (ID-based, master-table sourced) ----------------------

def _faculty_scope_user_id():
    """Returns the user_id to scope cascade results by, or None for admin
    (full access). Faculty see only courses/years/sections they are
    assigned to via StaffSectionMap."""
    if session.get('role') == 'faculty':
        return session.get('user_id')
    return None


@app.route('/api/v2/courses')
@login_required
def api_v2_courses():
    scope = _faculty_scope_user_id()
    conn = _v2_db(); cur = conn.cursor()
    if scope:
        cur.execute("""
            SELECT DISTINCT c.id, c.code, c.name
            FROM Courses c
            JOIN CourseYears cy ON cy.course_id = c.id
            JOIN Sections    s  ON s.course_year_id = cy.id
            JOIN StaffSectionMap m ON m.section_id = s.id
            WHERE m.user_id = %s AND c.is_active = TRUE AND s.is_active = TRUE
            ORDER BY c.name
        """, (scope,))
    else:
        cur.execute("SELECT id, code, name FROM Courses "
                    "WHERE is_active = TRUE ORDER BY name")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([{'id': r[0], 'code': r[1], 'name': r[2]} for r in rows])


@app.route('/api/v2/years')
@login_required
def api_v2_years():
    course_id = request.args.get('course_id', type=int)
    if not course_id:
        return jsonify([])
    scope = _faculty_scope_user_id()
    conn = _v2_db(); cur = conn.cursor()
    if scope:
        cur.execute("""
            SELECT DISTINCT cy.id, cy.year_number
            FROM CourseYears cy
            JOIN Sections    s  ON s.course_year_id = cy.id
            JOIN StaffSectionMap m ON m.section_id = s.id
            WHERE m.user_id = %s AND cy.course_id = %s AND s.is_active = TRUE
            ORDER BY cy.year_number
        """, (scope, course_id))
    else:
        cur.execute("SELECT id, year_number FROM CourseYears "
                    "WHERE course_id = %s ORDER BY year_number", (course_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([{'id': r[0], 'year_number': r[1]} for r in rows])


@app.route('/api/v2/sections')
@login_required
def api_v2_sections():
    cy_id = request.args.get('course_year_id', type=int)
    if not cy_id:
        return jsonify([])
    scope = _faculty_scope_user_id()
    conn = _v2_db(); cur = conn.cursor()
    if scope:
        cur.execute("""
            SELECT s.id, s.section_code, s.full_code
            FROM Sections s
            JOIN StaffSectionMap m ON m.section_id = s.id
            WHERE m.user_id = %s AND s.course_year_id = %s AND s.is_active = TRUE
            ORDER BY s.section_code
        """, (scope, cy_id))
    else:
        cur.execute("SELECT id, section_code, full_code FROM Sections "
                    "WHERE course_year_id = %s AND is_active = TRUE "
                    "ORDER BY section_code", (cy_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([{'id': r[0], 'section_code': r[1], 'full_code': r[2]}
                    for r in rows])


@app.route('/api/v2/batch')
@login_required
def api_v2_batch():
    section_id = request.args.get('section_id', type=int)
    if not section_id:
        return jsonify({'batch_id': None})
    faculty_id = (session.get('user_id')
                  if session.get('role') == 'faculty' else None)
    batch_id = find_or_create_batch_for_section(section_id, faculty_id)
    return jsonify({'batch_id': batch_id})


# ---- Attendance v3 API ----------------------------------------------------

def _parse_iso_date(s):
    try:
        return datetime.strptime(s, '%Y-%m-%d').date() if s else None
    except (TypeError, ValueError):
        return None


@app.route('/api/v3/attendance/my-sections')
@faculty_required
def api_v3_my_sections():
    """Sections the current user can mark attendance for.
    ?incharge_only=true narrows to General-Attendance-eligible sections."""
    incharge_only = request.args.get('incharge_only', '').lower() in ('1', 'true', 'yes')
    rows = get_my_sections(session['user_id'], role=session.get('role'),
                           incharge_only=incharge_only)
    return jsonify(rows)


@app.route('/api/v3/attendance/my-subjects')
@faculty_required
def api_v3_my_subjects():
    """Subjects this user can teach in the given section's course-year."""
    section_id = request.args.get('section_id', type=int)
    if not section_id:
        return jsonify([])
    rows = get_my_subjects(session['user_id'], section_id, role=session.get('role'))
    return jsonify(rows)


@app.route('/api/v3/sessions')
@faculty_required
def api_v3_sessions():
    """TimeSlots for the supplied date's day-of-week. Used by the subject
    attendance UI to populate the period selector."""
    date_str = request.args.get('date')
    target = _parse_iso_date(date_str) or datetime.now().date()
    day_name = target.strftime('%A')
    slots = [{'id': ts.id, 'period': ts.period, 'day': ts.day}
             for ts in get_timeslots() if ts.day == day_name]
    return jsonify(slots)


def _build_roster_context(*, attendance_type, section_id, date,
                         general_period=None, subject_id=None,
                         lab_id=None, session_id=None):
    """Shared between roster and mark for context/auth/lock computation."""
    role = session.get('role')
    user_id = session.get('user_id')
    allowed, deny_reason = can_mark_attendance(
        user_id, role, attendance_type, section_id,
        subject_id=subject_id, lab_id=lab_id,
    )
    date_ok, date_reason = can_mark_for_date(date, role)
    if not date_ok and allowed:
        deny_reason = date_reason
        allowed = False
    settings = get_attendance_settings()
    section = get_section_details(section_id)
    subject = None
    if subject_id:
        # cheap lookup; we already validated user has access in can_mark_attendance
        for s in get_my_subjects(user_id, section_id, role=role):
            if s['id'] == subject_id:
                subject = s; break
    return {
        'context': {
            'type': attendance_type,
            'section': section,
            'subject': subject,
            'general_period': general_period,
            'session_id': session_id,
            'date': date.isoformat() if date else None,
            'edit_window_hours': settings['edit_window_hours'],
            'can_mark': allowed,
            'deny_reason': deny_reason,
        },
        '_role': role,
        '_user_id': user_id,
        '_edit_window_hours': settings['edit_window_hours'],
    }


@app.route('/api/v3/attendance/roster')
@faculty_required
def api_v3_roster():
    """Returns the student list for a (type, section, date, period|subject+session)
    combo, with each student's current attendance status (if any), the lock
    flag, and a single can_mark context flag for the UI."""
    attendance_type = (request.args.get('type') or '').strip()
    section_id = request.args.get('section_id', type=int)
    date = _parse_iso_date(request.args.get('date'))
    general_period = request.args.get('general_period') or None
    subject_id = request.args.get('subject_id', type=int)
    lab_id = request.args.get('lab_id', type=int)
    session_id = request.args.get('session_id', type=int)

    if attendance_type not in ('general', 'subject', 'lab') or not section_id or not date:
        return jsonify({'error': 'missing or invalid args'}), 400

    built = _build_roster_context(
        attendance_type=attendance_type, section_id=section_id, date=date,
        general_period=general_period, subject_id=subject_id,
        lab_id=lab_id, session_id=session_id,
    )
    ctx = built['context']

    students = get_students_in_section(section_id)
    existing = {row[1]: row for row in get_attendance_v3(
        section_id, date, attendance_type,
        general_period=general_period, subject_id=subject_id,
        lab_id=lab_id, session_id=session_id,
    )}

    edit_window_hours = built['_edit_window_hours']
    now = datetime.now()
    roster = []
    for stu in students:
        e = existing.get(stu.id)
        if e:
            aid, _sid, status, marked_at = e
            locked = marked_at and (now - marked_at).total_seconds() > edit_window_hours * 3600
            roster.append({
                'id': stu.id, 'code': stu.student_code, 'name': stu.name,
                'current_status': status,
                'attendance_id': aid,
                'marked_at': marked_at.isoformat() if marked_at else None,
                'is_locked': bool(locked) and built['_role'] != 'admin',
            })
        else:
            roster.append({
                'id': stu.id, 'code': stu.student_code, 'name': stu.name,
                'current_status': None, 'attendance_id': None,
                'marked_at': None, 'is_locked': False,
            })
    return jsonify({'context': ctx, 'students': roster})


@app.route('/api/v3/attendance/mark', methods=['POST'])
@faculty_required
def api_v3_mark():
    """Upsert attendance for a (type, section, date, period|subject+session)
    combo. Body: {type, section_id, date, general_period?, subject_id?,
    lab_id?, session_id?, marks: [{student_id, status}, ...]}."""
    payload = request.get_json(silent=True) or {}
    attendance_type = (payload.get('type') or '').strip()
    section_id = payload.get('section_id')
    date = _parse_iso_date(payload.get('date'))
    general_period = payload.get('general_period') or None
    subject_id = payload.get('subject_id')
    lab_id = payload.get('lab_id')
    session_id = payload.get('session_id')
    marks = payload.get('marks') or []

    if attendance_type not in ('general', 'subject', 'lab'):
        return jsonify({'error': 'invalid type'}), 400
    if not section_id or not date or not isinstance(marks, list):
        return jsonify({'error': 'missing section_id/date/marks'}), 400

    role = session.get('role')
    user_id = session.get('user_id')

    allowed, reason = can_mark_attendance(
        user_id, role, attendance_type, section_id,
        subject_id=subject_id, lab_id=lab_id,
    )
    if not allowed:
        return jsonify({'error': 'unauthorized', 'reason': reason}), 403

    date_ok, date_reason = can_mark_for_date(date, role)
    if not date_ok:
        return jsonify({'error': 'backdating_disabled', 'reason': date_reason}), 422

    # Validate shape combos so we fail fast before any DB writes
    if attendance_type == 'general' and not general_period:
        return jsonify({'error': 'general_period required for general'}), 400
    if attendance_type == 'subject' and not (subject_id and session_id):
        return jsonify({'error': 'subject_id and session_id required'}), 400
    if attendance_type == 'lab' and not (lab_id and session_id):
        return jsonify({'error': 'lab_id and session_id required'}), 400

    # Pre-fetch existing rows so we can honor the lock window
    existing = {row[1]: row for row in get_attendance_v3(
        section_id, date, attendance_type,
        general_period=general_period, subject_id=subject_id,
        lab_id=lab_id, session_id=session_id,
    )}
    settings = get_attendance_settings()
    edit_window_hours = settings['edit_window_hours']
    now = datetime.now()

    saved = 0
    skipped_locked = 0
    absent_count = 0
    notifications_queued = 0
    errors = []
    for m in marks:
        student_id = m.get('student_id')
        status = (m.get('status') or '').strip().lower()
        if not student_id or status not in ('present', 'absent', 'late', 'leave'):
            errors.append(f"Bad mark for student_id={student_id}: status={status!r}")
            continue
        e = existing.get(student_id)
        if e and role != 'admin':
            _, _, _existing_status, marked_at = e
            if marked_at and (now - marked_at).total_seconds() > edit_window_hours * 3600:
                skipped_locked += 1
                continue
        try:
            attendance_id = save_attendance(
                student_id=student_id, date=date, status=status,
                marked_by=user_id,
                attendance_type=attendance_type,
                general_period=general_period,
                section_id=section_id, subject_id=subject_id, lab_id=lab_id,
                session_id=session_id,
            )
            saved += 1
            if status == 'absent':
                absent_count += 1
                # The worker thread dispatches these on its next tick.
                # UNIQUE(attendance_id, channel) prevents duplicate queue rows
                # when the mark is re-saved.
                try:
                    notifications_queued += enqueue_absent_notifications(
                        attendance_id, settings=settings,
                    )
                except Exception as exc:
                    errors.append(f"notify enqueue failed for student_id={student_id}: {exc}")
        except Exception as exc:
            errors.append(f"student_id={student_id}: {exc}")

    return jsonify({
        'saved': saved,
        'skipped_locked': skipped_locked,
        'absent_count': absent_count,
        'notifications_queued': notifications_queued,
        'errors': errors,
    })


@app.route('/api/availability')
def api_availability():
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({'error': 'Date required'})
    date = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    bookings = get_bookings_for_date(date)
    availability = []
    for booking in bookings:
        availability.append({
            'room_name': booking[2],
            'room_type': booking[3],
            'day': booking[4],
            'period': booking[5],
            'staff': booking[1]
        })
    return jsonify(availability)

# Attendance routes
@app.route('/attendance')
@faculty_required
def attendance_dashboard():
    """Entry chooser: lets the user pick General Attendance (section incharge)
    or Subject Attendance (subject teacher)."""
    role = session.get('role')
    user_id = session['user_id']
    incharge_sections = get_my_sections(user_id, role=role, incharge_only=True)
    all_sections = get_my_sections(user_id, role=role, incharge_only=False)
    # subjects available to the user across all their sections — used to show
    # a meaningful count on the Subject card without resolving sections first
    if role == 'admin':
        conn = _v2_db(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM Subjects WHERE is_active = TRUE")
        subject_count = cur.fetchone()[0]
        cur.close(); conn.close()
    else:
        conn = _v2_db(); cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(DISTINCT m.subject_id)
            FROM SubjectStaffMap m
            JOIN Subjects s ON s.id = m.subject_id
            WHERE m.user_id = %s AND s.is_active = TRUE
        """, (user_id,))
        subject_count = cur.fetchone()[0]
        cur.close(); conn.close()
    return render_template(
        'attendance_home.html',
        incharge_count=len(incharge_sections),
        assigned_count=len(all_sections),
        subject_count=subject_count,
        user=session,
    )


@app.route('/attendance/general')
@faculty_required
def attendance_general():
    """General attendance page — section incharge only. Section dropdown +
    period radio + roster grid. All data fetched via /api/v3 from JS."""
    role = session.get('role')
    sections = get_my_sections(session['user_id'], role=role, incharge_only=True)
    return render_template('attendance_general.html', sections=sections, user=session)


@app.route('/attendance/subject')
@faculty_required
def attendance_subject():
    """Subject attendance page — 4-step cascade + session selector."""
    role = session.get('role')
    sections = get_my_sections(session['user_id'], role=role, incharge_only=False)
    return render_template('attendance_subject.html', sections=sections, user=session)

@app.route('/attendance/mark/<int:batch_id>', methods=['GET', 'POST'])
@faculty_required
def mark_attendance(batch_id):
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    date = datetime.strptime(date_str, '%Y-%m-%d').date()
    session_id = request.args.get('session', None)
    if session_id:
        session_id = int(session_id)
    
    students = get_students(batch_id)
    existing_attendance = get_attendance(batch_id, date, session_id)
    attendance_dict = {a.student_id: a.status for a in existing_attendance}
    batch = next((b for b in get_batches() if b.id == batch_id), None)

    if request.method == 'POST':
        from models import period_from_session_id
        period = period_from_session_id(session_id)
        action = request.form.get('action')
        if action == 'mark_all_present':
            bulk_mark_attendance(batch_id, date, 'present', session['user_id'],
                                 attendance_type='general', general_period=period)
            flash('All students marked present.')
        elif action == 'mark_all_absent':
            bulk_mark_attendance(batch_id, date, 'absent', session['user_id'],
                                 attendance_type='general', general_period=period)
            flash('All students marked absent.')
        elif action == 'copy_previous':
            prev_date = date - timedelta(days=1)
            prev_attendance = get_attendance(batch_id, prev_date, session_id)
            if not prev_attendance:
                flash(f'No attendance found for {prev_date.strftime("%Y-%m-%d")} — nothing to copy.')
            else:
                for a in prev_attendance:
                    save_attendance(student_id=a.student_id, date=date,
                                    status=a.status, marked_by=session['user_id'],
                                    attendance_type='general', general_period=period,
                                    batch_id=batch_id)
                flash(f'Copied {len(prev_attendance)} records from {prev_date.strftime("%Y-%m-%d")}.')
        else:
            for student in students:
                status = request.form.get(f'status_{student.id}', 'absent')
                save_attendance(student_id=student.id, date=date,
                                status=status, marked_by=session['user_id'],
                                attendance_type='general', general_period=period,
                                batch_id=batch_id)
            flash('Attendance saved.')
        return redirect(url_for('mark_attendance', batch_id=batch_id, date=date_str, session=session_id))

    timeslots = get_timeslots()
    return render_template('mark_attendance.html', students=students, attendance=attendance_dict, date=date_str, session_id=session_id, timeslots=timeslots, batch_id=batch_id, batch=batch, user=session)

@app.route('/attendance/history/<int:student_id>')
@student_required
def attendance_history(student_id):
    # Check if student can view their own or faculty/admin can view any
    if session.get('role') == 'student':
        # For students, find their student_id
        from models import get_students
        students = get_students()
        user_students = [s for s in students if s.user_id == session['user_id']]
        if not user_students or user_students[0].id != student_id:
            flash('Access denied')
            return redirect(url_for('dashboard'))
    
    history = get_student_attendance_history(student_id)
    return render_template('attendance_history.html', history=history, user=session)

@app.route('/attendance/reports')
@faculty_required
def attendance_reports():
    """Reports landing — 4 report cards. Each links to a focused page."""
    return render_template('attendance_reports_home.html', user=session)


def _csv_response(filename, headers, rows, *, row_keys=None):
    """Generic CSV download. rows is a list of dicts; row_keys (in order)
    pick which fields to include and in what order."""
    import csv
    from io import StringIO
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(headers)
    for r in rows:
        if isinstance(r, dict):
            writer.writerow([r.get(k) for k in (row_keys or headers)])
        else:
            writer.writerow(r)
    resp = make_response(si.getvalue())
    resp.headers['Content-Disposition'] = f'attachment; filename={filename}'
    resp.headers['Content-Type'] = 'text/csv'
    return resp


@app.route('/attendance/reports/section')
@faculty_required
def attendance_report_section():
    section_id = request.args.get('section_id', type=int)
    from_date = request.args.get('from_date') or None
    to_date = request.args.get('to_date') or None
    include_archive = request.args.get('include_archive') == '1'
    export = request.args.get('export')
    rows = []
    section = None
    if section_id:
        rows = report_section_summary(section_id, from_date, to_date, include_archive)
        section = get_section_details(section_id)
    sections = get_my_sections(session['user_id'], role=session.get('role'))
    if export == 'csv' and rows:
        return _csv_response(
            f'section_{section_id}_attendance.csv',
            ['Student ID', 'Name', 'Present', 'Absent', 'Late', 'Leave', 'Total', '%'],
            rows,
            row_keys=['student_code', 'name', 'present', 'absent', 'late',
                      'leave', 'total', 'percentage'],
        )
    return render_template('attendance_report_section.html',
                           sections=sections, section=section, rows=rows,
                           from_date=from_date, to_date=to_date,
                           include_archive=include_archive, user=session)


@app.route('/attendance/reports/subject')
@faculty_required
def attendance_report_subject():
    subject_id = request.args.get('subject_id', type=int)
    from_date = request.args.get('from_date') or None
    to_date = request.args.get('to_date') or None
    include_archive = request.args.get('include_archive') == '1'
    export = request.args.get('export')
    rows = []
    subject = None
    if subject_id:
        rows = report_subject_summary(subject_id, from_date, to_date, include_archive)
        # cheap fetch for header
        conn = _v2_db(); cur = conn.cursor()
        cur.execute("""
            SELECT s.id, s.code, s.name, c.name AS course_name, cy.year_number
            FROM Subjects s
            JOIN CourseYears cy ON cy.id = s.course_year_id
            JOIN Courses c ON c.id = cy.course_id
            WHERE s.id = %s
        """, (subject_id,))
        r = cur.fetchone()
        cur.close(); conn.close()
        if r:
            subject = {'id': r[0], 'code': r[1], 'name': r[2],
                       'course_name': r[3], 'year_number': r[4]}
    # subjects available to this user (across all their sections)
    conn = _v2_db(); cur = conn.cursor()
    role = session.get('role')
    if role == 'admin':
        cur.execute("""
            SELECT s.id, s.code, s.name, c.name AS course_name, cy.year_number
            FROM Subjects s
            JOIN CourseYears cy ON cy.id = s.course_year_id
            JOIN Courses c ON c.id = cy.course_id
            WHERE s.is_active = TRUE
            ORDER BY c.name, cy.year_number, s.code
        """)
    else:
        cur.execute("""
            SELECT DISTINCT s.id, s.code, s.name, c.name AS course_name, cy.year_number
            FROM SubjectStaffMap m
            JOIN Subjects s ON s.id = m.subject_id
            JOIN CourseYears cy ON cy.id = s.course_year_id
            JOIN Courses c ON c.id = cy.course_id
            WHERE m.user_id = %s AND s.is_active = TRUE
            ORDER BY c.name, cy.year_number, s.code
        """, (session['user_id'],))
    subjects = [{'id': r[0], 'code': r[1], 'name': r[2],
                 'course_name': r[3], 'year_number': r[4]} for r in cur.fetchall()]
    cur.close(); conn.close()
    if export == 'csv' and rows:
        return _csv_response(
            f'subject_{subject_id}_attendance.csv',
            ['Student ID', 'Name', 'Section', 'Present', 'Absent', 'Late', 'Leave', 'Total', '%'],
            rows,
            row_keys=['student_code', 'name', 'section', 'present', 'absent',
                      'late', 'leave', 'total', 'percentage'],
        )
    return render_template('attendance_report_subject.html',
                           subjects=subjects, subject=subject, rows=rows,
                           from_date=from_date, to_date=to_date,
                           include_archive=include_archive, user=session)


@app.route('/attendance/reports/daily')
@faculty_required
def attendance_report_daily():
    date_str = request.args.get('date') or datetime.now().date().isoformat()
    section_id = request.args.get('section_id', type=int)
    include_archive = request.args.get('include_archive') == '1'
    export = request.args.get('export')
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        target_date = datetime.now().date()
        date_str = target_date.isoformat()
    rows = report_daily_absentees(target_date, section_id, include_archive)
    sections = get_my_sections(session['user_id'], role=session.get('role'))
    if export == 'csv':
        return _csv_response(
            f'absentees_{date_str}.csv',
            ['Student ID', 'Name', 'Section', 'Type', 'Period/Subject',
             'Parent Phone', 'Parent Email', 'Marked By'],
            [{
                'student_code': r['student_code'],
                'name': r['name'],
                'section_code': r['section_code'],
                'type': r['type'],
                'period_or_subject': (r['subject_name'] or '') if r['type'] != 'general'
                                     else (r['period'] or ''),
                'parent_phone': r['parent_phone'] or '',
                'parent_email': r['parent_email'] or '',
                'marked_by': r['marked_by_name'] or r['marked_by_username'] or '',
            } for r in rows],
            row_keys=['student_code', 'name', 'section_code', 'type',
                      'period_or_subject', 'parent_phone', 'parent_email', 'marked_by'],
        )
    return render_template('attendance_report_daily.html',
                           rows=rows, sections=sections,
                           date_str=date_str, section_id=section_id,
                           include_archive=include_archive, user=session)


@app.route('/attendance/reports/faculty')
@admin_required
def attendance_report_faculty():
    faculty_id = request.args.get('faculty_id', type=int)
    from_date = request.args.get('from_date') or None
    to_date = request.args.get('to_date') or None
    include_archive = request.args.get('include_archive') == '1'
    export = request.args.get('export')
    rows = report_faculty_activity(faculty_id, from_date, to_date, include_archive)
    faculty = list_faculty()  # (id, name, username)
    if export == 'csv':
        return _csv_response(
            f'faculty_activity_{faculty_id or "all"}.csv',
            ['Faculty', 'Username', 'Date', 'Type', 'Marks', 'Present', 'Absent'],
            rows,
            row_keys=['marked_by_name', 'username', 'date', 'type',
                      'marks', 'present', 'absent'],
        )
    return render_template('attendance_report_faculty.html',
                           rows=rows, faculty=faculty,
                           filter_faculty_id=faculty_id,
                           from_date=from_date, to_date=to_date,
                           include_archive=include_archive, user=session)


# ---- Absentee letters: eligibility ----------------------------------------

@app.route('/api/v3/letters/eligible')
@faculty_required
def api_v3_letters_eligible():
    """Returns the auto-detected continuous-absentee candidates for a
    section, plus each student's last-letter context. Only section incharge
    or admin may call."""
    section_id = request.args.get('section_id', type=int)
    if not section_id:
        return jsonify({'error': 'section_id required'}), 400
    role = session.get('role')
    user_id = session['user_id']
    allowed, reason = can_generate_absentee_letter(user_id, role, section_id)
    if not allowed:
        return jsonify({'error': 'unauthorized', 'reason': reason}), 403

    result = find_continuous_absentees(section_id)
    section = get_section_details(section_id)
    candidates_serialized = []
    for c in result['candidates']:
        stu = c['student']
        last = c['last_letter']
        candidates_serialized.append({
            'student': {
                'id': stu.id, 'name': stu.name,
                'student_code': stu.student_code,
                'parent_name': stu.parent_name,
                'parent_phone': stu.parent_phone,
                'address': stu.address,
                'has_address': c['has_address'],
                'has_parent': c['has_parent'],
            },
            'consecutive_days': c['consecutive_days'],
            'absent_from': c['absent_from'].isoformat() if c['absent_from'] else None,
            'absent_to':   c['absent_to'].isoformat()   if c['absent_to']   else None,
            'auto_selected': c['auto_selected'],
            'last_letter': ({
                'id': last['id'],
                'generated_at': last['generated_at'].isoformat() if last['generated_at'] else None,
                'absent_from': last['absent_from'].isoformat() if last['absent_from'] else None,
                'absent_to':   last['absent_to'].isoformat()   if last['absent_to']   else None,
                'consecutive_days': last['consecutive_days'],
            } if last else None),
        })
    return jsonify({
        'section': section,
        'threshold': result['threshold'],
        'lookback_days': result['lookback_days'],
        'weekend_days': result['weekend_days'],
        'as_of': datetime.now().date().isoformat(),
        'candidates': candidates_serialized,
    })


def _safe_filename(s, max_len=80):
    """Filesystem-safe slug for ZIP filenames inside generated archives."""
    import re
    s = re.sub(r'[^\w\-. ]+', '_', (s or '').strip())
    return (s[:max_len] or 'letter').strip('._')


@app.route('/api/v3/letters/generate', methods=['POST'])
@faculty_required
def api_v3_letters_generate():
    """Renders an absentee letter PDF for each selected student, persists a
    row + the PDF file, and streams a ZIP. Skips students without an address.

    Body: {section_id, student_ids:[], template_id?, letter_ref?}
    On all-skipped or all-failed, returns 207 JSON. On any success, streams
    the ZIP and includes a manifest in 'X-Letter-Manifest' header."""
    import hashlib, io, os as _os, zipfile, json as _json
    payload = request.get_json(silent=True) or {}
    section_id = payload.get('section_id')
    student_ids = payload.get('student_ids') or []
    template_id = payload.get('template_id')
    letter_ref = (payload.get('letter_ref') or '').strip() or None
    # Optional month scope: letter's monthly summary table is Jan -> through_month
    # of through_year. Defaults to current month of current year.
    through_year  = payload.get('through_year')
    through_month = payload.get('through_month')
    try:
        through_year  = int(through_year)  if through_year  is not None else None
        through_month = int(through_month) if through_month is not None else None
    except (TypeError, ValueError):
        return jsonify({'error': 'through_year/through_month must be integers'}), 400

    if not section_id or not isinstance(student_ids, list) or not student_ids:
        return jsonify({'error': 'section_id + non-empty student_ids required'}), 400

    role = session.get('role')
    user_id = session['user_id']
    allowed, reason = can_generate_absentee_letter(user_id, role, section_id)
    if not allowed:
        return jsonify({'error': 'unauthorized', 'reason': reason}), 403

    template = get_letter_template(template_id)
    if not template:
        return jsonify({'error': 'no_template',
                        'reason': 'No active letter template configured'}), 422

    section = get_section_details(section_id)
    # Re-run streak detection so we have authoritative day counts (also
    # protects against tampered client state).
    elig = find_continuous_absentees(section_id, min_consecutive=1)
    streaks = {c['student'].id: c for c in elig['candidates']}

    generated = []     # [(filename, pdf_bytes, letter_id, student_id)]
    skipped = []       # [{student_id, reason}]
    errors = []        # [{student_id, error}]

    letters_dir_rel = _os.path.join('static', 'letters',
                                    f"{datetime.now().year:04d}",
                                    f"{datetime.now().month:02d}")
    letters_dir_abs = _os.path.join(app.root_path, letters_dir_rel)
    _os.makedirs(letters_dir_abs, exist_ok=True)

    for sid in student_ids:
        try:
            sid_int = int(sid)
        except (TypeError, ValueError):
            errors.append({'student_id': sid, 'error': 'bad id'}); continue

        student = get_student_by_id(sid_int)
        if not student:
            skipped.append({'student_id': sid_int, 'reason': 'not_found'}); continue
        # Section guard — student must belong to the requested section
        if student.section_id != section_id:
            skipped.append({'student_id': sid_int, 'reason': 'wrong_section'}); continue
        if not student.address:
            skipped.append({'student_id': sid_int, 'reason': 'missing_address'}); continue

        streak = streaks.get(sid_int)
        consecutive_days = streak['consecutive_days'] if streak else 0
        absent_from = streak['absent_from'] if streak else datetime.now().date()
        absent_to   = streak['absent_to']   if streak else datetime.now().date()

        monthly = compute_monthly_summary(
            sid_int, section_id,
            year=through_year, through_month=through_month,
        )
        cumulative_pct = monthly[-1]['cumulative_pct'] if monthly else 0.0

        letter_meta = {
            'ref': letter_ref,
            'consecutive_days': consecutive_days,
            'absent_from': absent_from,
            'absent_from_str': absent_from.strftime('%d/%m/%Y') if absent_from else '—',
            'absent_to': absent_to,
            'absent_to_str': absent_to.strftime('%d/%m/%Y') if absent_to else '—',
        }
        try:
            html = _render_letter_html(
                student=student, section=section,
                monthly_summary=monthly,
                letter_meta=letter_meta, template=template,
            )
            pdf_bytes = _html_to_pdf_bytes(html)
        except Exception as exc:
            errors.append({'student_id': sid_int, 'error': f'render_failed: {exc}'})
            continue

        # Persist to disk
        slug = _safe_filename(f"{student.student_code or 'NA'}_{student.name}")
        filename_in_zip = f"{slug}.pdf"
        pdf_filename = f"{slug}_{int(datetime.now().timestamp())}.pdf"
        pdf_abs = _os.path.join(letters_dir_abs, pdf_filename)
        pdf_rel = _os.path.join(letters_dir_rel, pdf_filename).replace('\\', '/')
        try:
            with open(pdf_abs, 'wb') as f:
                f.write(pdf_bytes)
        except Exception as exc:
            errors.append({'student_id': sid_int, 'error': f'disk_write: {exc}'})
            continue

        sha = hashlib.sha256(pdf_bytes).hexdigest()
        snapshot = {
            'name': student.name, 'student_code': student.student_code,
            'parent_name': student.parent_name, 'address': student.address,
            'parent_phone': student.parent_phone, 'parent_email': student.parent_email,
            'phone': student.phone, 'email': student.email,
            'section_full_code': section['full_code'] if section else None,
        }
        try:
            letter_id = insert_absentee_letter_row(
                student_id=sid_int, section_id=section_id,
                template_id=template['id'],
                consecutive_days=consecutive_days,
                absent_from=absent_from, absent_to=absent_to,
                pdf_path=pdf_rel, sha256=sha,
                student_snapshot=snapshot,
                cumulative_pct=cumulative_pct,
                letter_ref=letter_ref, generated_by=user_id,
            )
        except Exception as exc:
            errors.append({'student_id': sid_int, 'error': f'db_insert: {exc}'})
            try: _os.remove(pdf_abs)
            except OSError: pass
            continue

        generated.append((filename_in_zip, pdf_bytes, letter_id, sid_int))

    if not generated:
        return jsonify({'generated': [], 'skipped': skipped, 'errors': errors}), 207

    # Bundle into a ZIP and stream
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename, pdf_bytes, _lid, _sid in generated:
            zf.writestr(filename, pdf_bytes)
    zbuf.seek(0)

    manifest = {
        'generated': [{'student_id': s, 'letter_id': l, 'filename': fn}
                      for (fn, _b, l, s) in generated],
        'skipped': skipped,
        'errors': errors,
    }
    section_label = (section['full_code'] if section else f'sec{section_id}')
    zip_name = f"absentee_letters_{section_label}_{datetime.now().date().isoformat()}.zip"
    resp = make_response(zbuf.read())
    resp.headers['Content-Type'] = 'application/zip'
    resp.headers['Content-Disposition'] = f'attachment; filename={zip_name}'
    resp.headers['X-Letter-Manifest'] = _json.dumps(manifest)
    return resp


@app.route('/api/v3/letters/<int:letter_id>/pdf')
@faculty_required
def api_v3_letter_pdf(letter_id):
    """Re-download a previously generated letter."""
    from flask import send_from_directory
    import os as _os
    rows = list_absentee_letters(limit=1)  # noop, just an alias for the import
    conn = _v2_db(); cur = conn.cursor()
    cur.execute("""SELECT pdf_path, section_id FROM AbsenteeLetters WHERE id = %s""",
                (letter_id,))
    r = cur.fetchone()
    cur.close(); conn.close()
    if not r:
        return jsonify({'error': 'not_found'}), 404
    pdf_path, section_id = r
    # Same gate as generation
    allowed, reason = can_generate_absentee_letter(
        session['user_id'], session.get('role'), section_id)
    if not allowed:
        return jsonify({'error': 'unauthorized', 'reason': reason}), 403
    full = _os.path.join(app.root_path, pdf_path)
    directory = _os.path.dirname(full)
    fname = _os.path.basename(full)
    return send_from_directory(directory, fname, mimetype='application/pdf')


@app.route('/api/v3/letters/<int:letter_id>/revoke', methods=['POST'])
@faculty_required
def api_v3_letter_revoke(letter_id):
    """Soft-revoke a letter. PDF stays on disk; row gets flagged with reason."""
    payload = request.get_json(silent=True) or {}
    reason = (payload.get('reason') or '').strip() or None
    conn = _v2_db(); cur = conn.cursor()
    cur.execute("""SELECT section_id, generated_by, generated_at FROM AbsenteeLetters
                   WHERE id = %s""", (letter_id,))
    r = cur.fetchone()
    cur.close(); conn.close()
    if not r:
        return jsonify({'error': 'not_found'}), 404
    section_id, gen_by, gen_at = r
    role = session.get('role')
    user_id = session['user_id']
    # Admin always; incharge only on own section within 24h of generation
    if role != 'admin':
        if not is_section_incharge(user_id, section_id):
            return jsonify({'error': 'unauthorized',
                            'reason': 'Only the section incharge or admin can revoke'}), 403
        from datetime import timedelta
        if datetime.now() - gen_at > timedelta(hours=24):
            return jsonify({'error': 'too_late',
                            'reason': '24h revoke window has expired; ask an admin'}), 403
    if revoke_absentee_letter(letter_id, user_id, reason=reason):
        return jsonify({'ok': True})
    return jsonify({'error': 'already_revoked'}), 409


@app.route('/admin/attendance/archive', methods=['POST'])
@admin_required
def admin_attendance_archive():
    """Manual trigger: moves >2y attendance to AttendanceArchive."""
    try:
        result = archive_old_attendance(cutoff_days=730)
        flash(f"Archived {result['attendance_rows_moved']} attendance row(s) "
              f"and {result['notification_rows_moved']} notification row(s) "
              f"older than {result['cutoff_date']}.")
    except Exception as exc:
        flash(f'Archival failed: {exc}')
    return redirect(url_for('admin_attendance_settings'))

@app.route('/attendance/export/<format>')
@faculty_required
def export_attendance(format):
    batch_id = request.args.get('batch_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    summary = get_attendance_summary(batch_id, start_date, end_date)
    
    if format == 'csv':
        # Generate CSV
        import csv
        from io import StringIO
        si = StringIO()
        writer = csv.writer(si)
        writer.writerow(['Student', 'Present', 'Absent', 'Late', 'Leave', 'Total'])
        for row in summary:
            writer.writerow(row)
        output = si.getvalue()
        response = make_response(output)
        response.headers['Content-Disposition'] = 'attachment; filename=attendance.csv'
        response.headers['Content-Type'] = 'text/csv'
        return response
    elif format == 'excel':
        # For Excel, need pandas
        import pandas as pd
        df = pd.DataFrame(summary, columns=['Student', 'Present', 'Absent', 'Late', 'Leave', 'Total'])
        from io import BytesIO
        bio = BytesIO()
        df.to_excel(bio, index=False)
        bio.seek(0)
        response = make_response(bio.getvalue())
        response.headers['Content-Disposition'] = 'attachment; filename=attendance.xlsx'
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return response
    # For PDF, need fpdf
    # Implement later

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )