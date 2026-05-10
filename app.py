from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, make_response
from models import create_tables, insert_sample_data, get_rooms, get_timeslots, get_bookings_for_date, make_booking, get_user, get_all_users, add_user, delete_user, cancel_booking, get_students, get_batches, get_attendance, mark_attendance as save_attendance, bulk_mark_attendance, get_student_attendance_history, get_attendance_summary
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
        # Find room_id and timeslot_id
        room_id = next(r.id for r in rooms if r.name == room_name)
        timeslot_id = next(ts.id for ts in timeslots if ts.day == day and ts.period == period)
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
        room_id = int(request.form['room_id'])
        timeslot_id = int(request.form['timeslot_id'])
        date_str = request.form['date']
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Get the timeslot details
        timeslots = get_timeslots()
        timeslot = next(ts for ts in timeslots if ts.id == timeslot_id)
        period = timeslot.period  # e.g., '9:00-10:00'
        start_hour = int(period.split('-')[0].split(':')[0])
        
        now = datetime.now()
        today = now.date()
        
        # Check if date is in the past
        if date < today:
            return "Cannot book for past dates."
        
        # If today, check if the period has already started
        if date == today and now.hour >= start_hour:
            return "Cannot book for past or current time slots."

        if timeslot.day != date.strftime('%A'):
            return f"Selected timeslot day ({timeslot.day}) does not match the chosen date ({date.strftime('%A')})."
        
        if make_booking(user_id, room_id, timeslot_id, date):
            return redirect(url_for('dashboard', date=date_str))
        else:
            return "Booking failed: Room already booked for that time."
    
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
    return redirect(url_for('dashboard'))

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
    batches = get_batches(session.get('user_id') if session.get('role') == 'faculty' else None)
    return render_template('attendance_dashboard.html', batches=batches, user=session)

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
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'mark_all_present':
            bulk_mark_attendance(batch_id, date, session_id, 'present', session['user_id'])
        elif action == 'mark_all_absent':
            bulk_mark_attendance(batch_id, date, session_id, 'absent', session['user_id'])
        elif action == 'copy_previous':
            # Copy from previous day
            prev_date = date - timedelta(days=1)
            prev_attendance = get_attendance(batch_id, prev_date, session_id)
            for a in prev_attendance:
                save_attendance(a.student_id, batch_id, date, session_id, a.status, session['user_id'])
        else:
            # Individual marking
            for student in students:
                status = request.form.get(f'status_{student.id}', 'absent')
                save_attendance(student.id, batch_id, date, session_id, status, session['user_id'])
        flash('Attendance marked successfully')
        return redirect(url_for('mark_attendance', batch_id=batch_id, date=date_str, session=session_id))
    
    timeslots = get_timeslots()
    return render_template('mark_attendance.html', students=students, attendance=attendance_dict, date=date_str, session_id=session_id, timeslots=timeslots, batch_id=batch_id, user=session)

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
    return render_template('attendance_reports.html', summary=summary, batches=batches, user=session)

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)