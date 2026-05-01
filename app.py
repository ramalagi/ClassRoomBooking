from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from models import create_tables, insert_sample_data, get_rooms, get_timeslots, get_bookings_for_date, make_booking, get_user, get_all_users, add_user, delete_user, cancel_booking
from datetime import datetime

import os

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'please_change_this_secret')

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
    # Default to today's date
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    date = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    rooms = get_rooms()
    timeslots = get_timeslots()
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
    return render_template('dashboard.html', grid=grid, rooms=rooms, timeslots=timeslots, date=date_str, today=today, user=session)

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
    
    # Filter timeslots for past prevention
    if date < today:
        filtered_timeslots = []
    elif date == today:
        filtered_timeslots = [ts for ts in timeslots if int(ts.period.split('-')[0].split(':')[0]) > now_hour]
    else:
        filtered_timeslots = timeslots
    
    return render_template('book.html', rooms=rooms, timeslots=filtered_timeslots, date=date_str, today=today, user=session)

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
            if add_user(username, password, role):
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)