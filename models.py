from db import get_db_connection
from collections import namedtuple

# Simple data classes for returned objects
Room = namedtuple('Room', ['id', 'name', 'type'])
TimeSlot = namedtuple('TimeSlot', ['id', 'day', 'period'])
Student = namedtuple('Student', ['id', 'user_id', 'name', 'email', 'batch_id',
                                 'student_code', 'parent_name', 'phone'])
Batch = namedtuple('Batch', ['id', 'name', 'faculty_id', 'course', 'year', 'section'])
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
            faculty_id INTEGER REFERENCES Users(id),
            course TEXT,
            year INTEGER,
            section TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Students (
            id SERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE REFERENCES Users(id),
            name TEXT NOT NULL,
            email TEXT,
            batch_id INTEGER REFERENCES Batches(id),
            student_code TEXT,
            parent_name TEXT,
            phone TEXT
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
    cursor.execute("ALTER TABLE Users    ADD COLUMN IF NOT EXISTS name TEXT")
    cursor.execute("ALTER TABLE Users    ADD COLUMN IF NOT EXISTS email TEXT")
    cursor.execute("ALTER TABLE Batches  ADD COLUMN IF NOT EXISTS course TEXT")
    cursor.execute("ALTER TABLE Batches  ADD COLUMN IF NOT EXISTS year INTEGER")
    cursor.execute("ALTER TABLE Batches  ADD COLUMN IF NOT EXISTS section TEXT")
    cursor.execute("ALTER TABLE Students ADD COLUMN IF NOT EXISTS student_code TEXT")
    cursor.execute("ALTER TABLE Students ADD COLUMN IF NOT EXISTS parent_name TEXT")
    cursor.execute("ALTER TABLE Students ADD COLUMN IF NOT EXISTS phone TEXT")
    cursor.execute("ALTER TABLE Students ALTER COLUMN user_id DROP NOT NULL")

    # Unique index on student_code so duplicates can't be inserted
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS students_student_code_unique "
        "ON Students (student_code) WHERE student_code IS NOT NULL"
    )

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
                "INSERT INTO Batches (name, faculty_id, course, year, section) "
                "VALUES (%s, %s, %s, %s, %s)",
                [
                    ('CS Year 1 - A', faculty_id, 'Computer Science', 1, 'A'),
                    ('CS Year 1 - B', faculty_id, 'Computer Science', 1, 'B'),
                ]
            )

    # Backfill legacy Batches rows that pre-date the course/year/section columns
    cursor.execute(
        "UPDATE Batches SET course = COALESCE(course, %s), "
        "year = COALESCE(year, %s), section = COALESCE(section, %s) "
        "WHERE course IS NULL OR year IS NULL OR section IS NULL",
        ('Computer Science', 1, 'A')
    )

    if _table_is_empty(cursor, 'Students'):
        cursor.execute("SELECT id FROM Batches ORDER BY id")
        batch_rows = cursor.fetchall()
        cursor.execute(
            "SELECT id, username FROM Users WHERE username IN ('student1','student2','student3')"
        )
        student_users = {row[1]: row[0] for row in cursor.fetchall()}
        if batch_rows and len(student_users) == 3:
            batch_a_id = batch_rows[0][0]
            batch_b_id = batch_rows[1][0] if len(batch_rows) > 1 else batch_a_id
            students = [
                (student_users['student1'], 'Student One', 'student1@nttf.com', batch_a_id,
                 'S001', 'Anand Kumar', '9876543210'),
                (student_users['student2'], 'Student Two', 'student2@nttf.com', batch_a_id,
                 'S002', 'Priya Sharma', '9876543211'),
                (student_users['student3'], 'Student Three', 'student3@nttf.com', batch_b_id,
                 'S003', 'Ravi Iyer', '9876543212'),
            ]
            cursor.executemany(
                "INSERT INTO Students "
                "(user_id, name, email, batch_id, student_code, parent_name, phone) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                students
            )

    # Backfill name/email for any pre-existing admin row seeded before
    # those columns existed (so the login session doesn't carry None values).
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
_STUDENT_COLS = "s.id, s.user_id, s.name, s.email, s.batch_id, s.student_code, s.parent_name, s.phone"
_BATCH_COLS = "id, name, faculty_id, course, year, section"


def _student_from_row(s):
    return Student(id=s[0], user_id=s[1], name=s[2], email=s[3], batch_id=s[4],
                   student_code=s[5], parent_name=s[6], phone=s[7])


def _batch_from_row(b):
    return Batch(id=b[0], name=b[1], faculty_id=b[2], course=b[3], year=b[4], section=b[5])


def get_students(batch_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if batch_id:
        cursor.execute(
            f"SELECT {_STUDENT_COLS} FROM Students s WHERE s.batch_id = %s ORDER BY s.id",
            (batch_id,)
        )
    else:
        cursor.execute(f"SELECT {_STUDENT_COLS} FROM Students s ORDER BY s.id")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [_student_from_row(r) for r in rows]


def get_batches(faculty_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if faculty_id:
        cursor.execute(
            f"SELECT {_BATCH_COLS} FROM Batches WHERE faculty_id = %s ORDER BY id",
            (faculty_id,)
        )
    else:
        cursor.execute(f"SELECT {_BATCH_COLS} FROM Batches ORDER BY id")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return [_batch_from_row(r) for r in rows]


# ---- Cascade getters: Course -> Year -> Section -> Batch ---------------------

def get_courses(faculty_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if faculty_id:
        cursor.execute(
            "SELECT DISTINCT course FROM Batches "
            "WHERE course IS NOT NULL AND faculty_id = %s ORDER BY course",
            (faculty_id,)
        )
    else:
        cursor.execute("SELECT DISTINCT course FROM Batches WHERE course IS NOT NULL ORDER BY course")
    courses = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return courses


def get_years_for_course(course, faculty_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    params = [course]
    sql = "SELECT DISTINCT year FROM Batches WHERE course = %s AND year IS NOT NULL"
    if faculty_id:
        sql += " AND faculty_id = %s"
        params.append(faculty_id)
    sql += " ORDER BY year"
    cursor.execute(sql, params)
    years = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return years


def get_sections_for_course_year(course, year, faculty_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    params = [course, year]
    sql = ("SELECT DISTINCT section FROM Batches "
           "WHERE course = %s AND year = %s AND section IS NOT NULL")
    if faculty_id:
        sql += " AND faculty_id = %s"
        params.append(faculty_id)
    sql += " ORDER BY section"
    cursor.execute(sql, params)
    sections = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return sections


def get_batch_by_course_year_section(course, year, section, faculty_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    params = [course, year, section]
    sql = (f"SELECT {_BATCH_COLS} FROM Batches "
           "WHERE course = %s AND year = %s AND section = %s")
    if faculty_id:
        sql += " AND faculty_id = %s"
        params.append(faculty_id)
    sql += " LIMIT 1"
    cursor.execute(sql, params)
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return _batch_from_row(row) if row else None


# ---- Batches admin ----------------------------------------------------------

def add_batch(name, course, year, section, faculty_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Batches (name, faculty_id, course, year, section) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (name, faculty_id, course, year, section)
        )
        batch_id = cursor.fetchone()[0]
        conn.commit()
        return batch_id
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def delete_batch(batch_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM Batches WHERE id = %s", (batch_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def find_or_create_batch(course, year, section, faculty_id=None):
    """Returns a batch id for the (course, year, section) triple,
    creating it if it doesn't exist."""
    existing = get_batch_by_course_year_section(course, year, section)
    if existing:
        return existing.id
    name = f"{course} - Year {year} - {section}"
    return add_batch(name, course, year, section, faculty_id)


# ---- Students admin ---------------------------------------------------------

def add_student(name, email, student_code, course, year, section,
                parent_name, phone, faculty_id=None):
    """Adds a student. Auto-creates the batch if needed. user_id stays NULL."""
    batch_id = find_or_create_batch(course, year, section, faculty_id)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Students "
            "(user_id, name, email, batch_id, student_code, parent_name, phone) "
            "VALUES (NULL, %s, %s, %s, %s, %s, %s) RETURNING id",
            (name, email, batch_id, student_code, parent_name, phone)
        )
        sid = cursor.fetchone()[0]
        conn.commit()
        return sid
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def delete_student(student_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Remove attendance rows first to avoid FK constraint
        cursor.execute("DELETE FROM Attendance WHERE student_id = %s", (student_id,))
        cursor.execute("DELETE FROM Students WHERE id = %s", (student_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def get_students_with_batch():
    """Returns rows joining Students + Batches for the admin list view."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.id, s.student_code, s.name, s.email, s.parent_name, s.phone,
               b.course, b.year, b.section, b.id
        FROM Students s
        LEFT JOIN Batches b ON s.batch_id = b.id
        ORDER BY b.course NULLS LAST, b.year NULLS LAST, b.section NULLS LAST, s.name
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def bulk_add_students(records):
    """records: list of dicts with keys: student_code, name, email, course,
    year, section, parent_name, phone. Returns (added, skipped, errors)."""
    added, skipped, errors = 0, 0, []
    existing_codes = set()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT student_code FROM Students WHERE student_code IS NOT NULL")
        existing_codes = {row[0] for row in cursor.fetchall()}
    finally:
        cursor.close()
        conn.close()

    for idx, rec in enumerate(records, start=2):  # row 1 is the header
        try:
            code = (rec.get('student_code') or '').strip()
            if not code:
                errors.append(f"Row {idx}: student_code is required")
                continue
            if code in existing_codes:
                skipped += 1
                continue
            name = (rec.get('name') or '').strip()
            if not name:
                errors.append(f"Row {idx}: name is required")
                continue
            year_raw = rec.get('year')
            try:
                year = int(year_raw) if year_raw not in (None, '') else None
            except (TypeError, ValueError):
                errors.append(f"Row {idx}: year must be a number (1/2/3)")
                continue
            course = (rec.get('course') or '').strip() or None
            section = (rec.get('section') or '').strip() or None
            if not (course and year and section):
                errors.append(f"Row {idx}: course, year and section are required")
                continue
            add_student(
                name=name,
                email=(rec.get('email') or '').strip() or None,
                student_code=code,
                course=course,
                year=year,
                section=section,
                parent_name=(rec.get('parent_name') or '').strip() or None,
                phone=(rec.get('phone') or '').strip() or None,
            )
            existing_codes.add(code)
            added += 1
        except Exception as exc:
            errors.append(f"Row {idx}: {exc}")
    return added, skipped, errors


def parse_students_xlsx(file_stream):
    """Parses an .xlsx file with a header row and the expected columns.
    Returns a list of dicts. Raises ValueError if required columns missing."""
    from openpyxl import load_workbook
    wb = load_workbook(file_stream, data_only=True, read_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        return []
    expected = ['student_code', 'name', 'email', 'course', 'year', 'section',
                'parent_name', 'phone']
    normalized = [str(h).strip().lower().replace(' ', '_') if h else '' for h in header]
    missing = [c for c in expected if c not in normalized]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    col_index = {c: normalized.index(c) for c in expected}
    records = []
    for row in rows:
        if row is None or all(v is None or str(v).strip() == '' for v in row):
            continue
        rec = {col: row[col_index[col]] for col in expected}
        records.append(rec)
    return records


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
