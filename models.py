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
    # When using local PostgreSQL, ensure the roombooking database exists.
    return


def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            name TEXT,
            email TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Rooms (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS TimeSlots (
            id SERIAL PRIMARY KEY,
            day TEXT NOT NULL,
            period TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Bookings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES Users(id),
            room_id INTEGER NOT NULL REFERENCES Rooms(id),
            timeslot_id INTEGER NOT NULL REFERENCES TimeSlots(id),
            date DATE NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Batches (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            faculty_id INTEGER REFERENCES Users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Students (
            id SERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE REFERENCES Users(id),
            name TEXT NOT NULL,
            email TEXT,
            batch_id INTEGER REFERENCES Batches(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Attendance (
            id SERIAL PRIMARY KEY,
            student_id INTEGER NOT NULL REFERENCES Students(id),
            batch_id INTEGER NOT NULL REFERENCES Batches(id),
            date DATE NOT NULL,
            session_id INTEGER REFERENCES TimeSlots(id),
            status TEXT NOT NULL,
            marked_by INTEGER NOT NULL REFERENCES Users(id),
            marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Unique index for upserts on attendance (treats NULL session_id as a single bucket)
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS attendance_unique_session
        ON Attendance (student_id, batch_id, date, session_id)
        WHERE session_id IS NOT NULL
    ''')
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS attendance_unique_no_session
        ON Attendance (student_id, batch_id, date)
        WHERE session_id IS NULL
    ''')

    # Idempotent schema migrations for tables that existed before these
    # columns were introduced. ADD COLUMN IF NOT EXISTS is safe to re-run.
    cursor.execute("ALTER TABLE Users ADD COLUMN IF NOT EXISTS name TEXT")
    cursor.execute("ALTER TABLE Users ADD COLUMN IF NOT EXISTS email TEXT")

    conn.commit()
    cursor.close()
    conn.close()


def _table_is_empty(cursor, table):
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    return cursor.fetchone()[0] == 0


def insert_sample_data():
    """Seed each table independently if it's empty. Safe to re-run."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if _table_is_empty(cursor, 'Users'):
        users = [
            ('admin', 'admin123', 'admin', 'Admin User', 'admin@nttf.com'),
            ('faculty1', 'faculty123', 'faculty', 'Faculty One', 'faculty1@nttf.com'),
            ('student1', 'student123', 'student', 'Student One', 'student1@nttf.com'),
            ('student2', 'student123', 'student', 'Student Two', 'student2@nttf.com'),
            ('student3', 'student123', 'student', 'Student Three', 'student3@nttf.com')
        ]
        cursor.executemany(
            "INSERT INTO Users (username, password, role, name, email) VALUES (%s, %s, %s, %s, %s)",
            users
        )

    if _table_is_empty(cursor, 'Rooms'):
        rooms = [
            ('Classroom 101', 'classroom'),
            ('Classroom 102', 'classroom'),
            ('Meeting Room A', 'meeting_room'),
            ('Meeting Room B', 'meeting_room')
        ]
        cursor.executemany("INSERT INTO Rooms (name, type) VALUES (%s, %s)", rooms)

    if _table_is_empty(cursor, 'TimeSlots'):
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        periods = ['9:00-10:00', '10:00-11:00', '11:00-12:00', '12:00-13:00',
                   '13:00-14:00', '14:00-15:00', '15:00-16:00', '16:00-17:00']
        timeslots = [(day, period) for day in days for period in periods]
        cursor.executemany("INSERT INTO TimeSlots (day, period) VALUES (%s, %s)", timeslots)

    if _table_is_empty(cursor, 'Batches'):
        cursor.execute("SELECT id FROM Users WHERE username = %s", ('faculty1',))
        row = cursor.fetchone()
        if row:
            faculty_id = row[0]
            cursor.executemany(
                "INSERT INTO Batches (name, faculty_id) VALUES (%s, %s)",
                [('Batch A', faculty_id), ('Batch B', faculty_id)]
            )

    if _table_is_empty(cursor, 'Students'):
        cursor.execute("SELECT id, name FROM Batches ORDER BY id")
        batch_rows = cursor.fetchall()
        cursor.execute(
            "SELECT id, username FROM Users WHERE username IN ('student1','student2','student3')"
        )
        student_users = {row[1]: row[0] for row in cursor.fetchall()}
        if batch_rows and len(student_users) == 3:
            batch_a_id = batch_rows[0][0]
            batch_b_id = batch_rows[1][0] if len(batch_rows) > 1 else batch_a_id
            students = [
                (student_users['student1'], 'Student One', 'student1@nttf.com', batch_a_id),
                (student_users['student2'], 'Student Two', 'student2@nttf.com', batch_a_id),
                (student_users['student3'], 'Student Three', 'student3@nttf.com', batch_b_id)
            ]
            cursor.executemany(
                "INSERT INTO Students (user_id, name, email, batch_id) VALUES (%s, %s, %s, %s)",
                students
            )

    # Backfill name/email for any pre-existing users seeded before those
    # columns existed (so the login session doesn't carry None values).
    cursor.execute(
        "UPDATE Users SET name = %s, email = %s WHERE username = %s AND (name IS NULL OR email IS NULL)",
        ('Admin User', 'admin@nttf.com', 'admin')
    )

    conn.commit()
    cursor.close()
    conn.close()


def get_rooms():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, type FROM Rooms ORDER BY id")
    rooms_data = cursor.fetchall()
    cursor.close()
    conn.close()
    return [Room(id=r[0], name=r[1], type=r[2]) for r in rooms_data]


def get_timeslots():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, day, period FROM TimeSlots ORDER BY id")
    timeslots_data = cursor.fetchall()
    cursor.close()
    conn.close()
    return [TimeSlot(id=ts[0], day=ts[1], period=ts[2]) for ts in timeslots_data]


def get_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, role, name, email FROM Users WHERE username = %s AND password = %s",
        (username, password)
    )
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user


def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, name, email FROM Users ORDER BY id")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return users


def add_user(username, password, role, name=None, email=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Users (username, password, role, name, email) VALUES (%s, %s, %s, %s, %s)",
            (username, password, role, name, email)
        )
        conn.commit()
        success = True
    except Exception:
        conn.rollback()
        success = False
    cursor.close()
    conn.close()
    return success


def delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM Users WHERE id = %s", (user_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
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
        WHERE b.date = %s
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
        WHERE room_id = %s AND timeslot_id = %s AND date = %s
    """, (room_id, timeslot_id, date))
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return count == 0


def make_booking(user_id, room_id, timeslot_id, date):
    if not check_availability(room_id, timeslot_id, date):
        return False

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO Bookings (user_id, room_id, timeslot_id, date)
            VALUES (%s, %s, %s, %s)
        """, (user_id, room_id, timeslot_id, date))
        conn.commit()
    except Exception:
        conn.rollback()
        cursor.close()
        conn.close()
        return False
    cursor.close()
    conn.close()
    return True


def cancel_booking(booking_id, user_id, is_admin=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    if is_admin:
        cursor.execute("DELETE FROM Bookings WHERE id = %s", (booking_id,))
    else:
        cursor.execute("DELETE FROM Bookings WHERE id = %s AND user_id = %s", (booking_id, user_id))
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
            WHERE s.batch_id = %s
            ORDER BY s.id
        """, (batch_id,))
    else:
        cursor.execute("""
            SELECT s.id, s.user_id, s.name, s.email, s.batch_id
            FROM Students s
            ORDER BY s.id
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
            SELECT id, name, faculty_id FROM Batches WHERE faculty_id = %s ORDER BY id
        """, (faculty_id,))
    else:
        cursor.execute("SELECT id, name, faculty_id FROM Batches ORDER BY id")
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
            WHERE a.batch_id = %s AND a.date = %s AND a.session_id = %s
        """, (batch_id, date, session_id))
    else:
        cursor.execute("""
            SELECT a.id, a.student_id, a.batch_id, a.date, a.session_id, a.status, a.marked_by
            FROM Attendance a
            WHERE a.batch_id = %s AND a.date = %s AND a.session_id IS NULL
        """, (batch_id, date))
    attendance_data = cursor.fetchall()
    cursor.close()
    conn.close()
    return [Attendance(id=a[0], student_id=a[1], batch_id=a[2], date=a[3], session_id=a[4], status=a[5], marked_by=a[6]) for a in attendance_data]


def mark_attendance(student_id, batch_id, date, session_id, status, marked_by):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if session_id is None:
            cursor.execute("""
                INSERT INTO Attendance (student_id, batch_id, date, session_id, status, marked_by, marked_at)
                VALUES (%s, %s, %s, NULL, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (student_id, batch_id, date) WHERE session_id IS NULL
                DO UPDATE SET status = EXCLUDED.status,
                              marked_by = EXCLUDED.marked_by,
                              marked_at = CURRENT_TIMESTAMP
            """, (student_id, batch_id, date, status, marked_by))
        else:
            cursor.execute("""
                INSERT INTO Attendance (student_id, batch_id, date, session_id, status, marked_by, marked_at)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (student_id, batch_id, date, session_id) WHERE session_id IS NOT NULL
                DO UPDATE SET status = EXCLUDED.status,
                              marked_by = EXCLUDED.marked_by,
                              marked_at = CURRENT_TIMESTAMP
            """, (student_id, batch_id, date, session_id, status, marked_by))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
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
        SELECT a.id, a.student_id, a.batch_id, a.date, a.session_id, a.status,
               u.username AS marked_by_name, a.marked_at, t.period
        FROM Attendance a
        LEFT JOIN Users u ON a.marked_by = u.id
        LEFT JOIN TimeSlots t ON a.session_id = t.id
        WHERE a.student_id = %s
    """
    params = [student_id]
    if start_date and end_date:
        query += " AND a.date BETWEEN %s AND %s"
        params.extend([start_date, end_date])
    query += " ORDER BY a.date DESC, a.marked_at DESC"
    cursor.execute(query, params)
    attendance_data = cursor.fetchall()
    cursor.close()
    conn.close()
    return attendance_data


def get_attendance_summary(batch_id=None, start_date=None, end_date=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT s.name,
               COALESCE(SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END), 0) AS present,
               COALESCE(SUM(CASE WHEN a.status = 'absent' THEN 1 ELSE 0 END), 0) AS absent,
               COALESCE(SUM(CASE WHEN a.status = 'late' THEN 1 ELSE 0 END), 0) AS late,
               COALESCE(SUM(CASE WHEN a.status = 'leave' THEN 1 ELSE 0 END), 0) AS leave_count,
               COUNT(a.id) AS total
        FROM Students s
        LEFT JOIN Attendance a ON s.id = a.student_id
    """
    params = []
    conditions = []
    if batch_id:
        conditions.append("s.batch_id = %s")
        params.append(batch_id)
    if start_date and end_date:
        conditions.append("(a.date IS NULL OR a.date BETWEEN %s AND %s)")
        params.extend([start_date, end_date])
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " GROUP BY s.id, s.name ORDER BY s.name"
    cursor.execute(query, params)
    summary = cursor.fetchall()
    cursor.close()
    conn.close()
    return summary
