from db import get_db_connection
from collections import namedtuple

# Simple data classes for returned objects
Room = namedtuple('Room', ['id', 'name', 'type'])
TimeSlot = namedtuple('TimeSlot', ['id', 'day', 'period'])
Student = namedtuple('Student', ['id', 'user_id', 'name', 'email', 'batch_id'])
Batch = namedtuple('Batch', ['id', 'name', 'faculty_id'])
Attendance = namedtuple('Attendance', ['id', 'student_id', 'batch_id', 'date', 'session_id', 'status', 'marked_by'])

def create_database():
    # PostgreSQL database creation is usually handled outside the app.
    # When using local PostgreSQL, ensure the RoomBooking database exists.
    return

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            name TEXT,
            email TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS TimeSlots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL,
            period TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            room_id INTEGER NOT NULL,
            timeslot_id INTEGER NOT NULL,
            date DATE NOT NULL,
            FOREIGN KEY (user_id) REFERENCES Users(id),
            FOREIGN KEY (room_id) REFERENCES Rooms(id),
            FOREIGN KEY (timeslot_id) REFERENCES TimeSlots(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            faculty_id INTEGER,
            FOREIGN KEY (faculty_id) REFERENCES Users(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            name TEXT NOT NULL,
            email TEXT,
            batch_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES Users(id),
            FOREIGN KEY (batch_id) REFERENCES Batches(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            batch_id INTEGER NOT NULL,
            date DATE NOT NULL,
            session_id INTEGER,  -- Optional, links to TimeSlots
            status TEXT NOT NULL,  -- present, absent, late, leave
            marked_by INTEGER NOT NULL,
            marked_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES Students(id),
            FOREIGN KEY (batch_id) REFERENCES Batches(id),
            FOREIGN KEY (session_id) REFERENCES TimeSlots(id),
            FOREIGN KEY (marked_by) REFERENCES Users(id)
        )
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()

def insert_sample_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM Users")
    if cursor.fetchone()[0] > 0:
        cursor.close()
        conn.close()
        return

    # Insert sample users
    users = [
        ('admin', 'admin123', 'admin', 'Admin User', 'admin@nttf.com'),
        ('faculty1', 'faculty123', 'faculty', 'Faculty One', 'faculty1@nttf.com'),
        ('student1', 'student123', 'student', 'Student One', 'student1@nttf.com'),
        ('student2', 'student123', 'student', 'Student Two', 'student2@nttf.com'),
        ('student3', 'student123', 'student', 'Student Three', 'student3@nttf.com')
    ]
    cursor.executemany("INSERT INTO Users (username, password, role, name, email) VALUES (?, ?, ?, ?, ?)", users)
    
    # Insert sample rooms
    rooms = [
        ('Classroom 101', 'classroom'),
        ('Classroom 102', 'classroom'),
        ('Meeting Room A', 'meeting_room'),
        ('Meeting Room B', 'meeting_room')
    ]
    cursor.executemany("INSERT INTO Rooms (name, type) VALUES (?, ?)", rooms)
    
    # Insert time slots for one week (assuming Monday to Friday, hourly periods from 9am to 5pm)
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    periods = ['9:00-10:00', '10:00-11:00', '11:00-12:00', '12:00-13:00', '13:00-14:00', '14:00-15:00', '15:00-16:00', '16:00-17:00']
    
    timeslots = []
    for day in days:
        for period in periods:
            timeslots.append((day, period))
    
    cursor.executemany("INSERT INTO TimeSlots (day, period) VALUES (?, ?)", timeslots)
    
    # Insert sample batches
    batches = [
        ('Batch A', 2),  # faculty1 id=2
        ('Batch B', 2)
    ]
    cursor.executemany("INSERT INTO Batches (name, faculty_id) VALUES (?, ?)", batches)
    
    # Insert sample students
    students = [
        (3, 'Student One', 'student1@nttf.com', 1),  # user_id=3, batch=1
        (4, 'Student Two', 'student2@nttf.com', 1),
        (5, 'Student Three', 'student3@nttf.com', 2)
    ]
    cursor.executemany("INSERT INTO Students (user_id, name, email, batch_id) VALUES (?, ?, ?, ?)", students)
    
    conn.commit()
    cursor.close()
    conn.close()

def get_rooms():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, type FROM Rooms")
    rooms_data = cursor.fetchall()
    cursor.close()
    conn.close()
    return [Room(id=r[0], name=r[1], type=r[2]) for r in rooms_data]

def get_timeslots():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, day, period FROM TimeSlots")
    timeslots_data = cursor.fetchall()
    cursor.close()
    conn.close()
    return [TimeSlot(id=ts[0], day=ts[1], period=ts[2]) for ts in timeslots_data]

def get_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, name, email FROM Users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, name, email FROM Users")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return users

def add_user(username, password, role, name=None, email=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO Users (username, password, role, name, email) VALUES (?, ?, ?, ?, ?)", (username, password, role, name, email))
        conn.commit()
        success = True
    except:
        success = False
    cursor.close()
    conn.close()
    return success

def delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM Users WHERE id = ?", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()

def get_bookings_for_date(date):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.id, u.username, r.name, r.type, t.day, t.period, b.date, u.id
        FROM Bookings b
        JOIN Users u ON b.user_id = u.id
        JOIN Rooms r ON b.room_id = r.id
        JOIN TimeSlots t ON b.timeslot_id = t.id
        WHERE b.date = ?
    """, (date,))
    bookings = cursor.fetchall()
    cursor.close()
    conn.close()
    return bookings

def check_availability(room_id, timeslot_id, date):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM Bookings
        WHERE room_id = ? AND timeslot_id = ? AND date = ?
    """, (room_id, timeslot_id, date))
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return count == 0

def make_booking(user_id, room_id, timeslot_id, date):
    if not check_availability(room_id, timeslot_id, date):
        return False  # Already booked
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Bookings (user_id, room_id, timeslot_id, date)
        VALUES (?, ?, ?, ?)
    """, (user_id, room_id, timeslot_id, date))
    conn.commit()
    cursor.close()
    conn.close()
    return True

def cancel_booking(booking_id, user_id, is_admin=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    if is_admin:
        cursor.execute("DELETE FROM Bookings WHERE id = ?", (booking_id,))
    else:
        cursor.execute("DELETE FROM Bookings WHERE id = ? AND user_id = ?", (booking_id, user_id))
    deleted = cursor.rowcount > 0
    conn.commit()
    cursor.close()
    conn.close()
    return deleted

# Attendance functions
def get_students(batch_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if batch_id:
        cursor.execute("""
            SELECT s.id, s.user_id, s.name, s.email, s.batch_id
            FROM Students s
            WHERE s.batch_id = ?
        """, (batch_id,))
    else:
        cursor.execute("""
            SELECT s.id, s.user_id, s.name, s.email, s.batch_id
            FROM Students s
        """)
    students_data = cursor.fetchall()
    cursor.close()
    conn.close()
    return [Student(id=s[0], user_id=s[1], name=s[2], email=s[3], batch_id=s[4]) for s in students_data]

def get_batches(faculty_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if faculty_id:
        cursor.execute("""
            SELECT id, name, faculty_id
            FROM Batches
            WHERE faculty_id = ?
        """, (faculty_id,))
    else:
        cursor.execute("""
            SELECT id, name, faculty_id
            FROM Batches
        """)
    batches_data = cursor.fetchall()
    cursor.close()
    conn.close()
    return [Batch(id=b[0], name=b[1], faculty_id=b[2]) for b in batches_data]

def get_attendance(batch_id, date, session_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if session_id:
        cursor.execute("""
            SELECT a.id, a.student_id, a.batch_id, a.date, a.session_id, a.status, a.marked_by
            FROM Attendance a
            WHERE a.batch_id = ? AND a.date = ? AND a.session_id = ?
        """, (batch_id, date, session_id))
    else:
        cursor.execute("""
            SELECT a.id, a.student_id, a.batch_id, a.date, a.session_id, a.status, a.marked_by
            FROM Attendance a
            WHERE a.batch_id = ? AND a.date = ?
        """, (batch_id, date))
    attendance_data = cursor.fetchall()
    cursor.close()
    conn.close()
    return [Attendance(id=a[0], student_id=a[1], batch_id=a[2], date=a[3], session_id=a[4], status=a[5], marked_by=a[6]) for a in attendance_data]

def mark_attendance(student_id, batch_id, date, session_id, status, marked_by):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO Attendance (id, student_id, batch_id, date, session_id, status, marked_by, marked_at)
        VALUES (
            (SELECT id FROM Attendance WHERE student_id = ? AND batch_id = ? AND date = ? AND (session_id = ? OR (session_id IS NULL AND ? IS NULL))),
            ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
        )
    """, (student_id, batch_id, date, session_id, session_id, student_id, batch_id, date, session_id, status, marked_by))
    conn.commit()
    cursor.close()
    conn.close()

def bulk_mark_attendance(batch_id, date, session_id, status, marked_by):
    students = get_students(batch_id)
    for student in students:
        mark_attendance(student.id, batch_id, date, session_id, status, marked_by)

def get_student_attendance_history(student_id, start_date=None, end_date=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT a.id, a.student_id, a.batch_id, a.date, a.session_id, a.status, a.marked_by, a.marked_at
        FROM Attendance a
        WHERE a.student_id = ?
    """
    params = [student_id]
    if start_date and end_date:
        query += " AND a.date BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    query += " ORDER BY a.date DESC, a.marked_at DESC"
    cursor.execute(query, params)
    attendance_data = cursor.fetchall()
    cursor.close()
    conn.close()
    return attendance_data  # Return raw data for history

def get_attendance_summary(batch_id=None, start_date=None, end_date=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT s.name, COALESCE(SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END), 0) as present,
               COALESCE(SUM(CASE WHEN a.status = 'absent' THEN 1 ELSE 0 END), 0) as absent,
               COALESCE(SUM(CASE WHEN a.status = 'late' THEN 1 ELSE 0 END), 0) as late,
               COALESCE(SUM(CASE WHEN a.status = 'leave' THEN 1 ELSE 0 END), 0) as leave,
               COUNT(a.id) as total
        FROM Students s
        LEFT JOIN Attendance a ON s.id = a.student_id
    """
    params = []
    if batch_id:
        query += " WHERE s.batch_id = ?"
        params.append(batch_id)
    if start_date and end_date:
        query += " AND a.date BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    query += " GROUP BY s.id, s.name"
    cursor.execute(query, params)
    summary = cursor.fetchall()
    cursor.close()
    conn.close()
    return summary