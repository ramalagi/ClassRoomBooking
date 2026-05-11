from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, make_response
from models import (
    create_tables, insert_sample_data, get_rooms, get_timeslots,
    get_bookings_for_date, make_booking, get_user, get_all_users, add_user,
    delete_user, cancel_booking, get_students, get_batches, get_attendance,
    mark_attendance as save_attendance, bulk_mark_attendance,
    get_student_attendance_history, get_attendance_summary,
    get_courses, get_years_for_course, get_sections_for_course_year,
    get_batch_by_course_year_section, add_batch, delete_batch,
    add_student, delete_student, get_students_with_batch,
    bulk_add_students, parse_students_xlsx,
)
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
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Initialize database automatically if needed.
with app.app_context():
    create_tables()
    insert_sample_data()

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
            username = request.form['username']
            password = request.form['password']
            role = request.form['role']
            name = request.form.get('name')
            email = request.form.get('email')
            if add_user(username, password, role, name, email):
                flash('User added')
            else:
                flash('User already exists')
        elif action == 'delete':
            user_id = int(request.form['user_id'])
            delete_user(user_id)
            flash('User deleted')
    users = get_all_users()
    return render_template('admin.html', users=users, user=session)


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


# ---- Admin: Students -------------------------------------------------------

@app.route('/admin/students', methods=['GET'])
@admin_required
def admin_students():
    students = get_students_with_batch()
    batches = get_batches()
    courses = sorted({b.course for b in batches if b.course})
    return render_template('admin_students.html',
                           students=students, batches=batches, courses=courses,
                           user=session)


@app.route('/admin/students/add', methods=['POST'])
@admin_required
def admin_add_student():
    try:
        name = (request.form.get('name') or '').strip()
        student_code = (request.form.get('student_code') or '').strip()
        email = (request.form.get('email') or '').strip() or None
        course = (request.form.get('course') or '').strip()
        section = (request.form.get('section') or '').strip()
        parent_name = (request.form.get('parent_name') or '').strip() or None
        phone = (request.form.get('phone') or '').strip() or None
        year = int(request.form.get('year'))
        if not (name and student_code and course and section and year):
            flash('Student ID, name, course, year and section are required.')
            return redirect(url_for('admin_students'))
        add_student(name=name, email=email, student_code=student_code,
                    course=course, year=year, section=section,
                    parent_name=parent_name, phone=phone)
        flash(f'Student "{name}" added.')
    except Exception as exc:
        flash(f'Could not add student: {exc}')
    return redirect(url_for('admin_students'))


@app.route('/admin/students/upload', methods=['POST'])
@admin_required
def admin_upload_students():
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
    added, skipped, errors = bulk_add_students(records)
    summary = f'Added {added} student(s).'
    if skipped:
        summary += f' Skipped {skipped} duplicate code(s).'
    if errors:
        summary += f' {len(errors)} row(s) had errors: ' + '; '.join(errors[:5])
        if len(errors) > 5:
            summary += f' (+{len(errors) - 5} more)'
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
               'parent_name', 'phone'])
    ws.append(['S101', 'Jane Doe', 'jane@nttf.com', 'Computer Science', 1, 'A',
               'John Doe', '9876543210'])
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
    faculty_id = _faculty_filter()
    courses = get_courses(faculty_id)
    return render_template('attendance_dashboard.html', courses=courses, user=session)

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
        action = request.form.get('action')
        if action == 'mark_all_present':
            bulk_mark_attendance(batch_id, date, session_id, 'present', session['user_id'])
            flash('All students marked present.')
        elif action == 'mark_all_absent':
            bulk_mark_attendance(batch_id, date, session_id, 'absent', session['user_id'])
            flash('All students marked absent.')
        elif action == 'copy_previous':
            prev_date = date - timedelta(days=1)
            prev_attendance = get_attendance(batch_id, prev_date, session_id)
            if not prev_attendance:
                flash(f'No attendance found for {prev_date.strftime("%Y-%m-%d")} — nothing to copy.')
            else:
                for a in prev_attendance:
                    save_attendance(a.student_id, batch_id, date, session_id, a.status, session['user_id'])
                flash(f'Copied {len(prev_attendance)} records from {prev_date.strftime("%Y-%m-%d")}.')
        else:
            for student in students:
                status = request.form.get(f'status_{student.id}', 'absent')
                save_attendance(student.id, batch_id, date, session_id, status, session['user_id'])
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
    batch_id = request.args.get('batch_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    summary = get_attendance_summary(batch_id, start_date, end_date)
    batches = get_batches()
    totals = {
        'present': sum((row[1] or 0) for row in summary),
        'absent':  sum((row[2] or 0) for row in summary),
        'late':    sum((row[3] or 0) for row in summary),
        'leave':   sum((row[4] or 0) for row in summary),
    }
    grand_total = sum(totals.values())
    return render_template('attendance_reports.html', summary=summary, batches=batches,
                           totals=totals, grand_total=grand_total, user=session)

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