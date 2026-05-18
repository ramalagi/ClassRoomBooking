from db import get_db_connection
from collections import namedtuple

# Simple data classes for returned objects
Room = namedtuple('Room', ['id', 'name', 'type'])
TimeSlot = namedtuple('TimeSlot', ['id', 'day', 'period'])
Student = namedtuple('Student', ['id', 'user_id', 'name', 'email', 'batch_id',
                                 'student_code', 'parent_name', 'phone', 'address',
                                 'section_id', 'parent_phone', 'parent_email'])
Batch = namedtuple('Batch', ['id', 'name', 'faculty_id', 'course', 'year', 'section'])
Attendance = namedtuple('Attendance', ['id', 'student_id', 'batch_id', 'date', 'session_id', 'status', 'marked_by'])

# Course Management master-data types
Course = namedtuple('Course', ['id', 'code', 'name', 'is_active'])
CourseYear = namedtuple('CourseYear', ['id', 'course_id', 'year_number'])
Section = namedtuple('Section', ['id', 'course_year_id', 'section_code', 'full_code',
                                 'incharge_id', 'is_active'])
Subject = namedtuple('Subject', ['id', 'course_year_id', 'code', 'name', 'credits', 'is_active'])
Lab = namedtuple('Lab', ['id', 'course_year_id', 'code', 'name', 'is_active'])
StaffSection = namedtuple('StaffSection', ['id', 'user_id', 'section_id', 'is_incharge'])
SubjectStaff = namedtuple('SubjectStaff', ['id', 'user_id', 'subject_id', 'is_incharge'])
LabStaff = namedtuple('LabStaff', ['id', 'user_id', 'lab_id', 'is_incharge'])


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

    # Legacy attendance unique indexes (batch-keyed) removed in Day 2 — the v3
    # partial unique indexes below replace them. See "Day 2 cleanup" further
    # down for the explicit DROP INDEX IF EXISTS statements.

    # Idempotent schema migrations for tables that existed before these
    # columns were introduced. ADD COLUMN IF NOT EXISTS is safe to re-run.
    cursor.execute("ALTER TABLE Users    ADD COLUMN IF NOT EXISTS name TEXT")
    cursor.execute("ALTER TABLE Users    ADD COLUMN IF NOT EXISTS email TEXT")
    cursor.execute("ALTER TABLE Users    ADD COLUMN IF NOT EXISTS must_change_password "
                   "BOOLEAN NOT NULL DEFAULT FALSE")
    cursor.execute("ALTER TABLE Batches  ADD COLUMN IF NOT EXISTS course TEXT")
    cursor.execute("ALTER TABLE Batches  ADD COLUMN IF NOT EXISTS year INTEGER")
    cursor.execute("ALTER TABLE Batches  ADD COLUMN IF NOT EXISTS section TEXT")
    cursor.execute("ALTER TABLE Students ADD COLUMN IF NOT EXISTS student_code TEXT")
    cursor.execute("ALTER TABLE Students ADD COLUMN IF NOT EXISTS parent_name TEXT")
    cursor.execute("ALTER TABLE Students ADD COLUMN IF NOT EXISTS phone TEXT")
    cursor.execute("ALTER TABLE Students ADD COLUMN IF NOT EXISTS address TEXT")
    cursor.execute("ALTER TABLE Students ALTER COLUMN user_id DROP NOT NULL")

    # Unique index on student_code so duplicates can't be inserted
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS students_student_code_unique "
        "ON Students (student_code) WHERE student_code IS NOT NULL"
    )

    # ---- Course Management master schema -----------------------------------
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Courses (
            id          SERIAL PRIMARY KEY,
            code        TEXT UNIQUE NOT NULL,
            name        TEXT NOT NULL,
            is_active   BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            created_by  INTEGER REFERENCES Users(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS CourseYears (
            id          SERIAL PRIMARY KEY,
            course_id   INTEGER NOT NULL REFERENCES Courses(id) ON DELETE CASCADE,
            year_number SMALLINT NOT NULL CHECK (year_number BETWEEN 1 AND 6),
            UNIQUE (course_id, year_number)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Sections (
            id              SERIAL PRIMARY KEY,
            course_year_id  INTEGER NOT NULL REFERENCES CourseYears(id) ON DELETE RESTRICT,
            section_code    TEXT NOT NULL,
            full_code       TEXT NOT NULL UNIQUE,
            incharge_id     INTEGER REFERENCES Users(id),
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (course_year_id, section_code)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Subjects (
            id              SERIAL PRIMARY KEY,
            course_year_id  INTEGER NOT NULL REFERENCES CourseYears(id) ON DELETE CASCADE,
            code            TEXT NOT NULL,
            name            TEXT NOT NULL,
            credits         SMALLINT,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            UNIQUE (course_year_id, code)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Labs (
            id              SERIAL PRIMARY KEY,
            course_year_id  INTEGER NOT NULL REFERENCES CourseYears(id) ON DELETE CASCADE,
            code            TEXT NOT NULL,
            name            TEXT NOT NULL,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            UNIQUE (course_year_id, code)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS StaffSectionMap (
            id           SERIAL PRIMARY KEY,
            user_id      INTEGER NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
            section_id   INTEGER NOT NULL REFERENCES Sections(id) ON DELETE CASCADE,
            is_incharge  BOOLEAN NOT NULL DEFAULT FALSE,
            assigned_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            assigned_by  INTEGER REFERENCES Users(id),
            UNIQUE (user_id, section_id)
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ssm_section ON StaffSectionMap(section_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ssm_user    ON StaffSectionMap(user_id)")
    # Single-incharge-per-section rule (Q1)
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uniq_section_incharge "
        "ON StaffSectionMap(section_id) WHERE is_incharge = TRUE"
    )

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS SubjectStaffMap (
            id           SERIAL PRIMARY KEY,
            user_id      INTEGER NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
            subject_id   INTEGER NOT NULL REFERENCES Subjects(id) ON DELETE CASCADE,
            is_incharge  BOOLEAN NOT NULL DEFAULT FALSE,
            assigned_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            assigned_by  INTEGER REFERENCES Users(id),
            UNIQUE (user_id, subject_id)
        )
    ''')
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uniq_subject_incharge "
        "ON SubjectStaffMap(subject_id) WHERE is_incharge = TRUE"
    )

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS LabStaffMap (
            id           SERIAL PRIMARY KEY,
            user_id      INTEGER NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
            lab_id       INTEGER NOT NULL REFERENCES Labs(id) ON DELETE CASCADE,
            is_incharge  BOOLEAN NOT NULL DEFAULT FALSE,
            assigned_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            assigned_by  INTEGER REFERENCES Users(id),
            UNIQUE (user_id, lab_id)
        )
    ''')
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uniq_lab_incharge "
        "ON LabStaffMap(lab_id) WHERE is_incharge = TRUE"
    )

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS AuditLog (
            id          BIGSERIAL PRIMARY KEY,
            entity      TEXT NOT NULL,
            entity_id   INTEGER,
            action      TEXT NOT NULL,
            actor_id    INTEGER REFERENCES Users(id),
            before_json JSONB,
            after_json  JSONB,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW()
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_entity ON AuditLog(entity, entity_id)")

    # Link existing rows to the new master schema. Kept alongside batch_id
    # while the legacy Batches table is still in use.
    cursor.execute("ALTER TABLE Students   ADD COLUMN IF NOT EXISTS section_id INTEGER REFERENCES Sections(id)")
    cursor.execute("ALTER TABLE Attendance ADD COLUMN IF NOT EXISTS section_id INTEGER REFERENCES Sections(id)")
    cursor.execute("ALTER TABLE Attendance ADD COLUMN IF NOT EXISTS subject_id INTEGER REFERENCES Subjects(id)")
    cursor.execute("ALTER TABLE Attendance ADD COLUMN IF NOT EXISTS lab_id     INTEGER REFERENCES Labs(id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_students_section ON Students(section_id)")

    # ---- Attendance Module v3 -------------------------------------------------
    # Discriminator: general / subject / lab. Defaults to 'general' so legacy
    # rows fall through cleanly during backfill.
    cursor.execute("ALTER TABLE Attendance ADD COLUMN IF NOT EXISTS "
                   "attendance_type TEXT NOT NULL DEFAULT 'general'")
    cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'attendance_type_check'
            ) THEN
                ALTER TABLE Attendance ADD CONSTRAINT attendance_type_check
                CHECK (attendance_type IN ('general', 'subject', 'lab'));
            END IF;
        END $$
    """)
    # Morning / Evening for general (Q3: two general per day, 9 AM and 4 PM)
    cursor.execute("ALTER TABLE Attendance ADD COLUMN IF NOT EXISTS general_period TEXT")
    cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'attendance_general_period_check'
            ) THEN
                ALTER TABLE Attendance ADD CONSTRAINT attendance_general_period_check
                CHECK (general_period IS NULL OR general_period IN ('morning', 'evening'));
            END IF;
        END $$
    """)

    # Three intent buckets, three partial unique indexes. Coexist with the
    # legacy batch-id-keyed indexes until mark_attendance is refactored (Day 2).
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS attendance_unique_subject_session "
        "ON Attendance (student_id, section_id, subject_id, date, session_id) "
        "WHERE subject_id IS NOT NULL"
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS attendance_unique_lab_session "
        "ON Attendance (student_id, section_id, lab_id, date, session_id) "
        "WHERE lab_id IS NOT NULL"
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS attendance_unique_general_period "
        "ON Attendance (student_id, section_id, date, general_period) "
        "WHERE attendance_type = 'general' AND general_period IS NOT NULL"
    )

    # Cross-column shape rule: which optional FKs are set must match the type.
    cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'attendance_shape_check') THEN
                ALTER TABLE Attendance ADD CONSTRAINT attendance_shape_check CHECK (
                    (attendance_type = 'general'
                       AND general_period IS NOT NULL AND session_id IS NULL
                       AND subject_id IS NULL AND lab_id IS NULL)
                    OR
                    (attendance_type = 'subject'
                       AND general_period IS NULL AND session_id IS NOT NULL
                       AND subject_id IS NOT NULL AND lab_id IS NULL)
                    OR
                    (attendance_type = 'lab'
                       AND general_period IS NULL AND session_id IS NOT NULL
                       AND lab_id IS NOT NULL AND subject_id IS NULL)
                );
            END IF;
        END $$
    """)

    # Day 2 cleanup: the v3 mark_attendance upsert now uses the new partial
    # unique indexes. The legacy batch-id-keyed indexes prevented morning+
    # evening coexistence — drop them now that nothing references them.
    cursor.execute("DROP INDEX IF EXISTS attendance_unique_session")
    cursor.execute("DROP INDEX IF EXISTS attendance_unique_no_session")

    # Per-student notification preferences (Q2). NULL notify_channels means
    # "inherit org default"; empty array means "do not notify this parent".
    cursor.execute("ALTER TABLE Students ADD COLUMN IF NOT EXISTS parent_phone TEXT")
    cursor.execute("ALTER TABLE Students ADD COLUMN IF NOT EXISTS parent_email TEXT")
    cursor.execute("ALTER TABLE Students ADD COLUMN IF NOT EXISTS notify_channels TEXT[]")

    # Singleton AttendanceSettings row (id=1 enforced by CHECK)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS AttendanceSettings (
            id                  SMALLINT PRIMARY KEY DEFAULT 1,
            edit_window_hours   INTEGER NOT NULL DEFAULT 24,
            allow_backdate_days INTEGER NOT NULL DEFAULT 0,
            notify_absent       BOOLEAN NOT NULL DEFAULT TRUE,
            notify_channels     TEXT[]  NOT NULL DEFAULT ARRAY['email']::TEXT[],
            message_template    TEXT NOT NULL DEFAULT
                'Dear Parent, your child {student_name} was marked absent on {date} for {context}. Please contact the institution for details.',
            updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_by          INTEGER REFERENCES Users(id),
            CHECK (id = 1)
        )
    ''')
    cursor.execute("INSERT INTO AttendanceSettings (id) VALUES (1) ON CONFLICT (id) DO NOTHING")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ParentNotifications (
            id              BIGSERIAL PRIMARY KEY,
            student_id      INTEGER NOT NULL REFERENCES Students(id) ON DELETE CASCADE,
            attendance_id   INTEGER NOT NULL REFERENCES Attendance(id) ON DELETE CASCADE,
            channel         TEXT NOT NULL,
            recipient       TEXT NOT NULL,
            message_body    TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'queued',
            provider        TEXT,
            provider_msg_id TEXT,
            attempt_count   SMALLINT NOT NULL DEFAULT 0,
            last_error      TEXT,
            last_attempt_at TIMESTAMP,
            queued_at       TIMESTAMP NOT NULL DEFAULT NOW(),
            sent_at         TIMESTAMP,
            CHECK (channel IN ('sms','whatsapp','email')),
            CHECK (status IN ('queued','sending','sent','failed','suppressed')),
            UNIQUE (attendance_id, channel)
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_parent_notif_status "
                   "ON ParentNotifications(status, queued_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_parent_notif_student "
                   "ON ParentNotifications(student_id)")

    # Retention archives (Q5: 2 years). Same shape as live tables;
    # FK constraints intentionally excluded so archived rows are stable.
    cursor.execute("CREATE TABLE IF NOT EXISTS AttendanceArchive "
                   "(LIKE Attendance INCLUDING DEFAULTS INCLUDING CONSTRAINTS)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_att_arch_student_date "
                   "ON AttendanceArchive(student_id, date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_att_arch_section_date "
                   "ON AttendanceArchive(section_id, date)")
    cursor.execute("CREATE TABLE IF NOT EXISTS ParentNotificationsArchive "
                   "(LIKE ParentNotifications INCLUDING DEFAULTS INCLUDING CONSTRAINTS)")

    # ---- Absentee letters (Day 5+) ---------------------------------------
    # Weekend + streak knobs. Default = only Sunday since Saturday is working
    # at this institution (Q1 confirmed).
    cursor.execute("ALTER TABLE AttendanceSettings ADD COLUMN IF NOT EXISTS "
                   "weekend_days TEXT[] NOT NULL DEFAULT ARRAY['Sunday']::TEXT[]")
    cursor.execute("ALTER TABLE AttendanceSettings ADD COLUMN IF NOT EXISTS "
                   "absentee_letter_threshold SMALLINT NOT NULL DEFAULT 3")
    cursor.execute("ALTER TABLE AttendanceSettings ADD COLUMN IF NOT EXISTS "
                   "absentee_letter_lookback_days SMALLINT NOT NULL DEFAULT 30")
    # Per-course-year override for weekends — NULL means inherit org default.
    cursor.execute("ALTER TABLE CourseYears ADD COLUMN IF NOT EXISTS "
                   "weekend_days_override TEXT[]")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Holidays (
            id          SERIAL PRIMARY KEY,
            date        DATE NOT NULL UNIQUE,
            name        TEXT NOT NULL,
            notes       TEXT,
            created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
            created_by  INTEGER REFERENCES Users(id)
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_holidays_date ON Holidays(date)")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS AbsenteeLetterTemplates (
            id              SERIAL PRIMARY KEY,
            name            TEXT NOT NULL,
            is_default      BOOLEAN NOT NULL DEFAULT FALSE,
            subject_line    TEXT NOT NULL DEFAULT 'IRREGULAR ATTENDANCE TO CLASS',
            body_html       TEXT NOT NULL,
            letterhead_path TEXT,
            signature_blocks TEXT[] NOT NULL DEFAULT
                ARRAY['SECTION I/C','COURSE INCHARGE','VICE PRINCIPAL','PRINCIPAL']::TEXT[],
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            created_by      INTEGER REFERENCES Users(id),
            updated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_by      INTEGER REFERENCES Users(id)
        )
    ''')
    # At most one default template
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uniq_letter_template_default "
        "ON AbsenteeLetterTemplates(is_default) WHERE is_default = TRUE"
    )

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS AbsenteeLetters (
            id                BIGSERIAL PRIMARY KEY,
            student_id        INTEGER NOT NULL REFERENCES Students(id) ON DELETE CASCADE,
            section_id        INTEGER NOT NULL REFERENCES Sections(id),
            template_id       INTEGER REFERENCES AbsenteeLetterTemplates(id) ON DELETE SET NULL,
            consecutive_days  INTEGER NOT NULL,
            absent_from       DATE NOT NULL,
            absent_to         DATE NOT NULL,
            letter_ref        TEXT,
            pdf_path          TEXT NOT NULL,
            sha256            TEXT,
            student_snapshot  JSONB NOT NULL,
            cumulative_pct    NUMERIC(5,2),
            generated_by      INTEGER NOT NULL REFERENCES Users(id),
            generated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            revoked_at        TIMESTAMP,
            revoked_by        INTEGER REFERENCES Users(id),
            revoked_reason    TEXT
        )
    ''')
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_letters_student_date "
                   "ON AbsenteeLetters(student_id, generated_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_letters_section "
                   "ON AbsenteeLetters(section_id, generated_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_letters_range "
                   "ON AbsenteeLetters(absent_from, absent_to)")

    conn.commit()
    cursor.close()
    conn.close()


def _table_is_empty(cursor, table):
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    return cursor.fetchone()[0] == 0


def _derive_course_code(name, taken):
    """Pick a stable, uppercased, alpha-only code. Falls back to numbered
    suffixes if the natural code clashes with one already in use."""
    import re
    base = re.sub(r'[^A-Za-z]', '', name or '').upper()[:4] or 'COURSE'
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


_DEFAULT_LETTER_BODY = """\
<p style="text-align:center;font-size:1.05rem;font-weight:bold;letter-spacing:.03em;">
NTTF TECHNICAL TRAINING FOUNDATION<br>
NTTF, {{ campus|default('CAMPUS') }}
</p>

<p>
TO,<br>
<strong>{{ student.parent_name|default('Parent / Guardian')|upper }}</strong><br>
{{ student.address|default('—') }}<br>
Mobile: {{ student.parent_phone or student.phone or '—' }}
</p>

<p style="text-align:right;">Date: {{ today_str }}</p>
{% if letter.ref %}<p>Ref: <strong>{{ letter.ref }}</strong></p>{% endif %}

<p style="text-align:center;text-decoration:underline;font-weight:bold;">
SUBJECT: {{ template.subject_line }}
</p>

<p>Dear Sir/Madam,</p>
<p>We regret to inform you that your son/daughter
<strong>{{ student.name|upper }}</strong>
({{ student.student_code or '—' }}) is having irregular attendance.
The details of number of absent days are given below:</p>

<table border="1" cellpadding="6" style="border-collapse:collapse;width:100%;font-size:.92rem;">
  <thead>
    <tr style="background:#f1f5f9;">
      <th>MONTH</th>
      <th>ABSENT DAYS</th>
      <th>PERCENTAGE FOR THE MONTH</th>
      <th>PERCENTAGE FOR THE YEAR (CUMULATIVE)</th>
    </tr>
  </thead>
  <tbody>
  {% for row in monthly_summary %}
    <tr>
      <td>{{ row.month }}</td>
      <td>{{ row.absent_days }}</td>
      <td>{{ '%.2f'|format(row.month_pct) }}%</td>
      <td>{{ '%.2f'|format(row.cumulative_pct) }}%</td>
    </tr>
  {% endfor %}
  </tbody>
</table>

<p style="margin-top:1rem;">
Your ward is continuously absent for the last
<strong>{{ letter.consecutive_days }}</strong> days
({{ letter.absent_from_str }} → {{ letter.absent_to_str }}).
</p>

<p>You have failed to send information about your absence. In-spite of our counseling/phone
calls, you are not responding and not informing about your absence. Due to your above
absence, you may not able to meet the attendance criteria.</p>

<p>You are hereby informed that in terms of para 2.3.1 of NTTF academic rules and
regulation, for trainees, attendance of a minimum 90% in a semester is needed to be
eligible to write semester's exam. Otherwise, the trainee will not be allowed to write
examination. Also, you are hereby informed that in terms of para 2.1 of NTTF rules and
regulation for trainees, if a trainee is absent from training consecutively for 8 days,
he/she will be considered as having voluntarily left and abandoned training and treated
as termination from training at this institution.</p>

<p>In the view of the above, you are asked to meet the Section incharge and Manager
along with this Letter and give proper explanation letter. Also meet Principal without
fail. Thanking you.</p>

<table style="width:100%;margin-top:60px;border-collapse:collapse;">
  <tr>
  {% for block in template.signature_blocks %}
    <td style="text-align:center;padding-top:48px;font-size:.85rem;">
      ____________________<br>
      <strong>{{ block }}</strong>
    </td>
  {% endfor %}
  </tr>
</table>
"""


def seed_default_letter_template():
    """Inserts the canonical 'Standard 3-Day Warning' template if none exists.
    Idempotent — only inserts when the table is empty."""
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM AbsenteeLetterTemplates")
        if cur.fetchone()[0] == 0:
            cur.execute("""
                INSERT INTO AbsenteeLetterTemplates
                  (name, is_default, subject_line, body_html)
                VALUES (%s, TRUE, %s, %s)
            """, ('Standard Continuous Absence Warning',
                  'IRREGULAR ATTENDANCE TO CLASS',
                  _DEFAULT_LETTER_BODY))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def backfill_attendance_v3():
    """Idempotent migration of legacy Attendance rows into the v3 shape:
    every row without a subject/lab is 'general', and inherits a morning/
    evening period from its session_id (or defaults to 'morning')."""
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE Attendance
            SET attendance_type = 'general'
            WHERE subject_id IS NULL AND lab_id IS NULL
              AND attendance_type IS DISTINCT FROM 'general'
        """)
        cur.execute("""
            UPDATE Attendance a
            SET general_period = COALESCE(
                (SELECT CASE
                    WHEN CAST(SPLIT_PART(t.period, ':', 1) AS INTEGER) < 13
                        THEN 'morning'
                    ELSE 'evening'
                 END
                 FROM TimeSlots t WHERE t.id = a.session_id),
                'morning'
            )
            WHERE a.attendance_type = 'general'
              AND a.general_period IS NULL
        """)
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def backfill_course_master():
    """One-way migration: lift legacy free-text (course, year, section) on
    Batches into the new Courses/CourseYears/Sections master tables and link
    Students.section_id / Attendance.section_id. Idempotent."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Courses ---------------------------------------------------------
        cursor.execute("SELECT code, name FROM Courses")
        existing = cursor.fetchall()
        taken_codes = {row[0] for row in existing}
        existing_names = {row[1] for row in existing}

        cursor.execute(
            "SELECT DISTINCT course FROM Batches "
            "WHERE course IS NOT NULL AND course <> ''"
        )
        for (course_name,) in cursor.fetchall():
            if course_name in existing_names:
                continue
            code = _derive_course_code(course_name, taken_codes)
            taken_codes.add(code)
            cursor.execute(
                "INSERT INTO Courses (code, name) VALUES (%s, %s) "
                "ON CONFLICT (code) DO NOTHING",
                (code, course_name)
            )

        # CourseYears -----------------------------------------------------
        cursor.execute("""
            INSERT INTO CourseYears (course_id, year_number)
            SELECT DISTINCT c.id, b.year
            FROM Batches b
            JOIN Courses c ON c.name = b.course
            WHERE b.year IS NOT NULL
            ON CONFLICT (course_id, year_number) DO NOTHING
        """)

        # Sections — full_code uses the unique course.code as prefix so
        # two courses starting with the same letter can't collide
        cursor.execute("""
            INSERT INTO Sections (course_year_id, section_code, full_code)
            SELECT cy.id, b.section,
                   c.code || b.year::text || b.section
            FROM Batches b
            JOIN Courses c      ON c.name = b.course
            JOIN CourseYears cy ON cy.course_id = c.id
                               AND cy.year_number = b.year
            WHERE b.section IS NOT NULL AND b.section <> ''
            ON CONFLICT (full_code) DO NOTHING
        """)

        # Students.section_id from legacy batch_id ------------------------
        cursor.execute("""
            UPDATE Students s SET section_id = sec.id
            FROM Batches b
            JOIN Courses c      ON c.name = b.course
            JOIN CourseYears cy ON cy.course_id = c.id
                               AND cy.year_number = b.year
            JOIN Sections sec   ON sec.course_year_id = cy.id
                               AND sec.section_code = b.section
            WHERE s.batch_id = b.id AND s.section_id IS NULL
        """)

        # Attendance.section_id from the linked student ------------------
        cursor.execute("""
            UPDATE Attendance a SET section_id = s.section_id
            FROM Students s
            WHERE a.student_id = s.id
              AND a.section_id IS NULL
              AND s.section_id IS NOT NULL
        """)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


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
    """Returns (id, username, role, name, email, must_change_password) on a
    successful match, else None."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, role, name, email, must_change_password "
        "FROM Users WHERE username = %s AND password = %s",
        (username, password)
    )
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user


def generate_temp_password(length=12):
    """Cryptographically random alphanumeric (no easily-confused chars)."""
    import secrets, string
    alphabet = ''.join(c for c in (string.ascii_letters + string.digits)
                       if c not in '0OIl1')
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def add_staff_with_temp_password(username, role, name=None, email=None,
                                 actor_id=None):
    """Creates a staff user with an auto-generated temp password and the
    must_change_password flag set. Returns (user_id, temp_password) on
    success, (None, None) on duplicate username."""
    if role not in ('admin', 'faculty'):
        raise ValueError("role must be 'admin' or 'faculty'")
    temp = generate_temp_password()
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO Users (username, password, role, name, email, "
            " must_change_password) "
            "VALUES (%s, %s, %s, %s, %s, TRUE) RETURNING id",
            (username, temp, role, name, email)
        )
        uid = cur.fetchone()[0]
        _audit(cur, 'user', uid, 'create',
               after={'username': username, 'role': role, 'email': email,
                      'must_change_password': True},
               actor_id=actor_id)
        conn.commit()
        return uid, temp
    except Exception:
        conn.rollback()
        return None, None
    finally:
        cur.close(); conn.close()


def set_user_password(user_id, new_password, must_change=False):
    """Updates a user's password and the must_change flag. Used by the
    self-service /account/password endpoint."""
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE Users SET password = %s, must_change_password = %s "
            "WHERE id = %s",
            (new_password, bool(must_change), user_id)
        )
        ok = cur.rowcount > 0
        _audit(cur, 'user', user_id, 'change_password',
               after={'must_change_password': bool(must_change)},
               actor_id=user_id)
        conn.commit()
        return ok
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def reset_user_password(user_id, actor_id=None):
    """Admin-triggered: generate a fresh temp password, flip must_change_password
    on, and return (username, email, temp_password) for the email step. Returns
    None if user doesn't exist."""
    temp = generate_temp_password()
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT username, email FROM Users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        cur.execute(
            "UPDATE Users SET password = %s, must_change_password = TRUE "
            "WHERE id = %s",
            (temp, user_id)
        )
        _audit(cur, 'user', user_id, 'reset_password',
               after={'by_admin': True}, actor_id=actor_id)
        conn.commit()
        return row[0], row[1], temp
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, name, email FROM Users ORDER BY id")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return users


def get_user_incharge_sections():
    """Returns {user_id: [{course, full_code, section_code}, ...]} for every
    user who is currently marked incharge of at least one section. Used to
    annotate the admin Users table."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT m.user_id, c.name, s.full_code, s.section_code
        FROM StaffSectionMap m
        JOIN Sections     s  ON s.id = m.section_id
        JOIN CourseYears  cy ON cy.id = s.course_year_id
        JOIN Courses      c  ON c.id = cy.course_id
        WHERE m.is_incharge = TRUE
        ORDER BY c.name, s.full_code
    """)
    out = {}
    for uid, course_name, full_code, section_code in cur.fetchall():
        out.setdefault(uid, []).append({
            'course': course_name,
            'full_code': full_code,
            'section_code': section_code,
        })
    cur.close(); conn.close()
    return out


def list_faculty():
    """Returns (id, name, username) tuples for staff eligible to be assigned
    to sections — admins and faculty. Admins included so a single-admin tenant
    can still assign themselves as incharge during setup."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, username FROM Users "
        "WHERE role IN ('faculty', 'admin') "
        "ORDER BY COALESCE(name, username)"
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


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
_STUDENT_COLS = ("s.id, s.user_id, s.name, s.email, s.batch_id, "
                 "s.student_code, s.parent_name, s.phone, s.address, "
                 "s.section_id, s.parent_phone, s.parent_email")
_BATCH_COLS = "id, name, faculty_id, course, year, section"


def _student_from_row(s):
    return Student(id=s[0], user_id=s[1], name=s[2], email=s[3], batch_id=s[4],
                   student_code=s[5], parent_name=s[6], phone=s[7],
                   address=s[8], section_id=s[9],
                   parent_phone=s[10], parent_email=s[11])


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


def find_or_create_batch_for_section(section_id, faculty_id=None):
    """Master-table aware: given a Sections.id, resolve to the matching
    Batches row (legacy attendance/booking still keys off batch_id). Creates
    the Batches row on demand if no compatible one exists."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT c.name, cy.year_number, s.section_code
        FROM Sections s
        JOIN CourseYears cy ON cy.id = s.course_year_id
        JOIN Courses     c  ON c.id  = cy.course_id
        WHERE s.id = %s
    """, (section_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return None
    course_name, year_number, section_code = row
    return find_or_create_batch(course_name, year_number, section_code, faculty_id)


# ---- Students admin ---------------------------------------------------------

def add_student(name, email, student_code, parent_name, phone, address=None,
                section_id=None, actor_id=None):
    """Adds a student. If section_id is given, also resolves and stores the
    legacy batch_id so attendance/booking paths keep working. user_id stays
    NULL (students don't get login accounts here)."""
    batch_id = (find_or_create_batch_for_section(section_id)
                if section_id is not None else None)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Students "
            "(user_id, name, email, student_code, parent_name, phone, address, "
            " section_id, batch_id) "
            "VALUES (NULL, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (name, email, student_code, parent_name, phone, address,
             section_id, batch_id)
        )
        sid = cursor.fetchone()[0]
        if actor_id is not None:
            _audit(cursor, 'student', sid, 'create',
                   after={'name': name, 'student_code': student_code,
                          'section_id': section_id},
                   actor_id=actor_id)
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
    """Returns rows joining Students + Batches for the admin list view.
    Tuple shape: (id, student_code, name, email, parent_name, phone,
                  course, year, section, batch_id, address)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.id, s.student_code, s.name, s.email, s.parent_name, s.phone,
               b.course, b.year, b.section, b.id, s.address
        FROM Students s
        LEFT JOIN Batches b ON s.batch_id = b.id
        ORDER BY b.course NULLS LAST, b.year NULLS LAST, b.section NULLS LAST, s.name
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def validate_student_rows(records):
    """Annotates each record with a verdict against the master Course/Year/
    Section tables. Pure read — no inserts.

    Verdicts:
      ok        — fully resolved to a master Section
      warn      — accepted as unassigned (Q4: partial or empty section info)
      error     — rejected (missing required, invalid year, or all three
                  section fields filled but no matching master record)
      duplicate — student_code already exists in the DB or earlier in this file

    Returns {'rows': [...], 'summary': {...}}."""
    courses_by_name = {c.name.strip().upper(): c for c in list_courses()}
    course_year_ids = {}   # (course_id, year_number) -> course_year_id
    section_by_key  = {}   # (course_year_id, section_code_upper) -> Section
    for course in courses_by_name.values():
        for cy in list_course_years(course.id):
            course_year_ids[(course.id, cy.year_number)] = cy.id
            for sec in list_sections(course_year_id=cy.id):
                section_by_key[(cy.id, sec.section_code.upper())] = sec

    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT student_code FROM Students WHERE student_code IS NOT NULL")
    existing_codes = {r[0] for r in cur.fetchall()}
    cur.close(); conn.close()
    seen_codes = set()

    rows = []
    for idx, rec in enumerate(records, start=2):
        code = (rec.get('student_code') or '')
        code = str(code).strip() if code is not None else ''
        name = str(rec.get('name') or '').strip()
        course_str = str(rec.get('course') or '').strip()
        section_str = str(rec.get('section') or '').strip()
        year_raw = rec.get('year')
        try:
            year_parsed = int(year_raw) if year_raw not in (None, '') else None
            year_bad = False
        except (TypeError, ValueError):
            year_parsed, year_bad = None, True

        # Preserve the raw value (incl. invalid like 'abc') so that
        # re-validation during commit produces the same verdict.
        row = {
            'row_index':    idx,
            'student_code': code,
            'name':         name,
            'email':        str(rec.get('email') or '').strip() or None,
            'parent_name':  str(rec.get('parent_name') or '').strip() or None,
            'phone':        str(rec.get('phone') or '').strip() or None,
            'address':      str(rec.get('address') or '').strip() or None,
            'course':       course_str,
            'year':         year_raw if year_bad else year_parsed,
            'section':      section_str,
            'section_id':   None,
            'verdict':      'ok',
            'reason':       '',
        }

        if not code:
            row.update(verdict='error', reason='student_code is required')
        elif not name:
            row.update(verdict='error', reason='name is required')
        elif code in existing_codes:
            row.update(verdict='duplicate',
                       reason=f"student_code '{code}' already exists in DB")
        elif code in seen_codes:
            row.update(verdict='duplicate',
                       reason=f"student_code '{code}' is duplicated within this file")
        elif year_bad or (year_parsed is not None and not (1 <= year_parsed <= 6)):
            row.update(verdict='error', reason='year must be a number between 1 and 6')
        else:
            seen_codes.add(code)
            filled = sum(bool(x) for x in (course_str, year_parsed, section_str))
            if filled == 3:
                course_obj = courses_by_name.get(course_str.upper())
                if not course_obj:
                    row.update(verdict='error',
                               reason=f"course '{course_str}' is not in master data")
                else:
                    cy_id = course_year_ids.get((course_obj.id, year_parsed))
                    if not cy_id:
                        row.update(verdict='error',
                                   reason=f"Year {year_parsed} is not configured for {course_str}")
                    else:
                        sec = section_by_key.get((cy_id, section_str.upper()))
                        if not sec:
                            row.update(verdict='error',
                                       reason=f"section '{section_str}' is not configured "
                                              f"for {course_str} Year {year_parsed}")
                        else:
                            row['section_id'] = sec.id
                            row['verdict'] = 'ok'
            elif filled == 0:
                row.update(verdict='warn', reason='no section info — will be unassigned')
            else:
                row.update(verdict='warn',
                           reason='partial section info — will be unassigned')
        rows.append(row)

    summary = {
        'valid':      sum(1 for r in rows if r['verdict'] == 'ok'),
        'unassigned': sum(1 for r in rows if r['verdict'] == 'warn'),
        'errors':     sum(1 for r in rows if r['verdict'] == 'error'),
        'duplicates': sum(1 for r in rows if r['verdict'] == 'duplicate'),
        'total':      len(rows),
    }
    return {'rows': rows, 'summary': summary}


def commit_validated_students(rows, actor_id=None):
    """Inserts rows where verdict ∈ {'ok','warn'}. Re-validates against the
    current master tables (defense against tampered hidden form data).

    Returns (inserted, skipped, errors_list)."""
    revalidated = validate_student_rows([{
        'student_code': r.get('student_code'),
        'name':         r.get('name'),
        'email':        r.get('email'),
        'course':       r.get('course'),
        'year':         r.get('year'),
        'section':      r.get('section'),
        'parent_name':  r.get('parent_name'),
        'phone':        r.get('phone'),
        'address':      r.get('address'),
    } for r in rows])

    inserted, skipped, errors = 0, 0, []
    conn = get_db_connection(); cur = conn.cursor()
    try:
        for r in revalidated['rows']:
            if r['verdict'] in ('error', 'duplicate'):
                skipped += 1
                continue
            try:
                # Also resolve the legacy batch_id so attendance/booking
                # paths keep working for bulk-uploaded students.
                batch_id = (find_or_create_batch_for_section(r['section_id'])
                            if r['section_id'] is not None else None)
                cur.execute(
                    "INSERT INTO Students "
                    "(user_id, name, email, student_code, parent_name, phone, "
                    " address, section_id, batch_id) "
                    "VALUES (NULL, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (r['name'], r['email'], r['student_code'],
                     r['parent_name'], r['phone'], r['address'],
                     r['section_id'], batch_id)
                )
                inserted += 1
            except Exception as exc:
                errors.append(f"Row {r['row_index']}: {exc}")
                conn.rollback()
                cur = conn.cursor()
        if actor_id is not None:
            _audit(cur, 'student_upload', None, 'commit',
                   after={'inserted': inserted, 'skipped': skipped},
                   actor_id=actor_id)
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()
    return inserted, skipped, errors


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
    required = ['student_code', 'name', 'email', 'course', 'year', 'section',
                'parent_name', 'phone']
    optional = ['address']  # accepted but not enforced — old files keep working
    normalized = [str(h).strip().lower().replace(' ', '_') if h else '' for h in header]
    missing = [c for c in required if c not in normalized]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    col_index = {c: normalized.index(c) for c in required}
    for c in optional:
        if c in normalized:
            col_index[c] = normalized.index(c)
    records = []
    for row in rows:
        if row is None or all(v is None or str(v).strip() == '' for v in row):
            continue
        rec = {col: (row[col_index[col]] if col in col_index else None)
               for col in required + optional}
        records.append(rec)
    return records


def period_from_session_id(session_id):
    """Translates a legacy TimeSlots.id into a v3 general_period.
    Slots that start before 13:00 are 'morning', everything else 'evening'.
    NULL session_id defaults to 'morning'. Used by the legacy mark UI."""
    if not session_id:
        return 'morning'
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT period FROM TimeSlots WHERE id = %s", (session_id,))
    r = cur.fetchone()
    cur.close(); conn.close()
    if not r:
        return 'morning'
    try:
        start_hour = int(r[0].split(':')[0].split('-')[0])
    except (ValueError, IndexError):
        return 'morning'
    return 'morning' if start_hour < 13 else 'evening'


def get_attendance(batch_id, date, session_id=None):
    """v3-aware fetch for the legacy mark-attendance UI. The legacy session_id
    parameter is interpreted as a general_period hint (morning/evening)."""
    period = period_from_session_id(session_id)
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT a.id, a.student_id, a.batch_id, a.date, a.session_id, a.status, a.marked_by
        FROM Attendance a
        WHERE a.batch_id = %s AND a.date = %s
          AND a.attendance_type = 'general'
          AND a.general_period = %s
    """, (batch_id, date, period))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [Attendance(id=a[0], student_id=a[1], batch_id=a[2], date=a[3],
                       session_id=a[4], status=a[5], marked_by=a[6]) for a in rows]


# ---- Attendance v3: settings, authorization, lock window ------------------

def get_attendance_settings():
    """Read the singleton AttendanceSettings row. Returns a plain dict."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT edit_window_hours, allow_backdate_days, notify_absent,
               notify_channels, message_template,
               weekend_days, absentee_letter_threshold,
               absentee_letter_lookback_days
        FROM AttendanceSettings WHERE id = 1
    """)
    r = cur.fetchone()
    cur.close(); conn.close()
    if not r:
        return {'edit_window_hours': 24, 'allow_backdate_days': 0,
                'notify_absent': True, 'notify_channels': ['email'],
                'message_template': '',
                'weekend_days': ['Sunday'],
                'absentee_letter_threshold': 3,
                'absentee_letter_lookback_days': 30}
    return {'edit_window_hours': r[0], 'allow_backdate_days': r[1],
            'notify_absent': r[2], 'notify_channels': list(r[3] or []),
            'message_template': r[4],
            'weekend_days': list(r[5] or []),
            'absentee_letter_threshold': r[6],
            'absentee_letter_lookback_days': r[7]}


def _exists(sql, params):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(sql, params)
    out = cur.fetchone() is not None
    cur.close(); conn.close()
    return out


def is_section_incharge(user_id, section_id):
    return _exists(
        "SELECT 1 FROM StaffSectionMap "
        "WHERE user_id = %s AND section_id = %s AND is_incharge = TRUE",
        (user_id, section_id)
    )


def is_assigned_to_section(user_id, section_id):
    return _exists(
        "SELECT 1 FROM StaffSectionMap WHERE user_id = %s AND section_id = %s",
        (user_id, section_id)
    )


def is_assigned_to_subject(user_id, subject_id):
    return _exists(
        "SELECT 1 FROM SubjectStaffMap WHERE user_id = %s AND subject_id = %s",
        (user_id, subject_id)
    )


def is_assigned_to_lab(user_id, lab_id):
    return _exists(
        "SELECT 1 FROM LabStaffMap WHERE user_id = %s AND lab_id = %s",
        (user_id, lab_id)
    )


def can_mark_attendance(user_id, role, attendance_type, section_id,
                        subject_id=None, lab_id=None):
    """Returns (allowed: bool, reason: str|None). Drives every mark/edit gate."""
    if role == 'admin':
        return True, None
    if role != 'faculty':
        return False, 'Not a staff account'
    if not section_id:
        return False, 'section_id is required'
    if attendance_type == 'general':
        if is_section_incharge(user_id, section_id):
            return True, None
        return False, 'You are not the incharge of this section'
    if attendance_type == 'subject':
        if not subject_id:
            return False, 'subject_id is required for subject attendance'
        if not is_assigned_to_section(user_id, section_id):
            return False, 'You are not assigned to this section'
        if not is_assigned_to_subject(user_id, subject_id):
            return False, 'You are not assigned to this subject'
        return True, None
    if attendance_type == 'lab':
        if not lab_id:
            return False, 'lab_id is required for lab attendance'
        if not is_assigned_to_section(user_id, section_id):
            return False, 'You are not assigned to this section'
        if not is_assigned_to_lab(user_id, lab_id):
            return False, 'You are not assigned to this lab'
        return True, None
    return False, f'Unknown attendance type: {attendance_type}'


def can_mark_for_date(target_date, role):
    """Backdating gate (Q1: faculty=today-only; admin can backdate up to
    allow_backdate_days). Returns (allowed: bool, reason: str|None)."""
    from datetime import date as _d, timedelta
    today = _d.today()
    if target_date > today:
        return False, 'Cannot mark attendance for future dates'
    if role == 'admin':
        settings = get_attendance_settings()
        if today - target_date > timedelta(days=settings['allow_backdate_days']):
            return False, (f"Backdating limited to {settings['allow_backdate_days']} days. "
                           "Adjust 'allow_backdate_days' in attendance settings if needed.")
        return True, None
    if target_date != today:
        return False, 'Backdating is disabled. Faculty can mark today only.'
    return True, None


def is_attendance_locked(attendance_id):
    """True if a row is past the configured edit window."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT marked_at + make_interval(hours => s.edit_window_hours) < NOW()
        FROM Attendance a, AttendanceSettings s
        WHERE a.id = %s AND s.id = 1
    """, (attendance_id,))
    r = cur.fetchone()
    cur.close(); conn.close()
    return bool(r and r[0])


def get_students_in_section(section_id):
    """Returns Students rows for a Section. Falls back to legacy batch_id
    join when a Student.section_id hasn't been linked yet."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(f"""
        SELECT {_STUDENT_COLS} FROM Students s
        WHERE s.section_id = %s ORDER BY s.name
    """, (section_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [_student_from_row(r) for r in rows]


def get_attendance_v3(section_id, date, attendance_type,
                     general_period=None, subject_id=None,
                     lab_id=None, session_id=None):
    """Returns existing attendance rows matching the v3 filter. Each row is
    (attendance_id, student_id, status, marked_at). Used by the roster
    endpoint to pre-fill current_status."""
    conn = get_db_connection(); cur = conn.cursor()
    if attendance_type == 'general':
        cur.execute("""
            SELECT id, student_id, status, marked_at
            FROM Attendance
            WHERE section_id = %s AND date = %s
              AND attendance_type = 'general' AND general_period = %s
        """, (section_id, date, general_period))
    elif attendance_type == 'subject':
        cur.execute("""
            SELECT id, student_id, status, marked_at
            FROM Attendance
            WHERE section_id = %s AND date = %s
              AND attendance_type = 'subject'
              AND subject_id = %s AND session_id = %s
        """, (section_id, date, subject_id, session_id))
    elif attendance_type == 'lab':
        cur.execute("""
            SELECT id, student_id, status, marked_at
            FROM Attendance
            WHERE section_id = %s AND date = %s
              AND attendance_type = 'lab'
              AND lab_id = %s AND session_id = %s
        """, (section_id, date, lab_id, session_id))
    else:
        cur.close(); conn.close()
        return []
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def get_my_sections(user_id, role='faculty', incharge_only=False):
    """Sections this user can mark attendance for.
    - admin: all active sections (incharge_only has no effect)
    - faculty: their StaffSectionMap entries, optionally narrowed to incharge"""
    conn = get_db_connection(); cur = conn.cursor()
    if role == 'admin':
        cur.execute("""
            SELECT s.id, s.full_code, s.section_code, c.name, cy.year_number,
                   FALSE
            FROM Sections s
            JOIN CourseYears cy ON cy.id = s.course_year_id
            JOIN Courses     c  ON c.id = cy.course_id
            WHERE s.is_active = TRUE AND c.is_active = TRUE
            ORDER BY c.name, cy.year_number, s.section_code
        """)
    else:
        sql = """
            SELECT s.id, s.full_code, s.section_code, c.name, cy.year_number,
                   m.is_incharge
            FROM StaffSectionMap m
            JOIN Sections     s  ON s.id = m.section_id
            JOIN CourseYears  cy ON cy.id = s.course_year_id
            JOIN Courses      c  ON c.id = cy.course_id
            WHERE m.user_id = %s AND s.is_active = TRUE AND c.is_active = TRUE
        """
        params = [user_id]
        if incharge_only:
            sql += " AND m.is_incharge = TRUE"
        sql += " ORDER BY c.name, cy.year_number, s.section_code"
        cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{
        'id':           r[0], 'full_code':   r[1], 'section_code': r[2],
        'course_name':  r[3], 'year_number': r[4], 'is_incharge':  bool(r[5]),
    } for r in rows]


def get_my_subjects(user_id, section_id, role='faculty'):
    """Subjects this user can teach in the given section's course-year.
    Admin sees every active subject for the course-year."""
    conn = get_db_connection(); cur = conn.cursor()
    if role == 'admin':
        cur.execute("""
            SELECT s.id, s.code, s.name, FALSE
            FROM Subjects s
            WHERE s.is_active = TRUE
              AND s.course_year_id = (SELECT course_year_id FROM Sections WHERE id = %s)
            ORDER BY s.code
        """, (section_id,))
    else:
        cur.execute("""
            SELECT s.id, s.code, s.name, m.is_incharge
            FROM SubjectStaffMap m
            JOIN Subjects s ON s.id = m.subject_id
            WHERE m.user_id = %s AND s.is_active = TRUE
              AND s.course_year_id = (SELECT course_year_id FROM Sections WHERE id = %s)
            ORDER BY s.code
        """, (user_id, section_id))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{
        'id': r[0], 'code': r[1], 'name': r[2], 'is_incharge': bool(r[3])
    } for r in rows]


def get_section_details(section_id):
    """Returns a flat dict of (id, full_code, section_code, course, year, is_active)
    or None when the section doesn't exist."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT s.id, s.full_code, s.section_code, c.name, cy.year_number,
               s.is_active
        FROM Sections     s
        JOIN CourseYears  cy ON cy.id = s.course_year_id
        JOIN Courses      c  ON c.id = cy.course_id
        WHERE s.id = %s
    """, (section_id,))
    r = cur.fetchone()
    cur.close(); conn.close()
    if not r:
        return None
    return {'id': r[0], 'full_code': r[1], 'section_code': r[2],
            'course_name': r[3], 'year_number': r[4], 'is_active': r[5]}


def get_section_id_for_batch(batch_id):
    """Resolves a legacy Batches.id to the corresponding Sections.id (1:1
    after the course-master backfill)."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT s.id FROM Batches b
        JOIN Courses c      ON c.name = b.course
        JOIN CourseYears cy ON cy.course_id = c.id AND cy.year_number = b.year
        JOIN Sections s     ON s.course_year_id = cy.id AND s.section_code = b.section
        WHERE b.id = %s
    """, (batch_id,))
    r = cur.fetchone()
    cur.close(); conn.close()
    return r[0] if r else None


# ---- Attendance v3: upsert ------------------------------------------------

def mark_attendance(student_id, date, status, marked_by, *,
                    attendance_type='general', general_period='morning',
                    section_id=None, subject_id=None, lab_id=None,
                    session_id=None, batch_id=None):
    """Upsert a single attendance row using the v3 partial unique indexes.

    Resolves section_id from batch_id or Students.section_id if not given.
    Validates the shape (which FKs must be set) before insert."""
    if section_id is None and batch_id is not None:
        section_id = get_section_id_for_batch(batch_id)
    if section_id is None:
        conn = get_db_connection(); cur = conn.cursor()
        cur.execute("SELECT section_id FROM Students WHERE id = %s", (student_id,))
        r = cur.fetchone(); cur.close(); conn.close()
        section_id = r[0] if r else None
    if section_id is None:
        raise ValueError("section_id required (not resolvable from student/batch)")
    # batch_id stays NOT NULL on the legacy Attendance schema, so make sure
    # we have one — the find_or_create helper handles both legacy + new flow.
    if batch_id is None:
        batch_id = find_or_create_batch_for_section(section_id)

    if attendance_type == 'general':
        if general_period not in ('morning', 'evening'):
            raise ValueError("general_period must be 'morning' or 'evening'")
        subject_id = lab_id = session_id = None
    elif attendance_type == 'subject':
        if not (subject_id and session_id):
            raise ValueError("subject_id and session_id required for subject attendance")
        lab_id = None
        general_period = None
    elif attendance_type == 'lab':
        if not (lab_id and session_id):
            raise ValueError("lab_id and session_id required for lab attendance")
        subject_id = None
        general_period = None
    else:
        raise ValueError(f"unknown attendance_type: {attendance_type}")

    conn = get_db_connection(); cur = conn.cursor()
    try:
        if attendance_type == 'general':
            cur.execute("""
                INSERT INTO Attendance
                  (student_id, section_id, batch_id, date, status, marked_by, marked_at,
                   attendance_type, general_period)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, 'general', %s)
                ON CONFLICT (student_id, section_id, date, general_period)
                WHERE attendance_type = 'general' AND general_period IS NOT NULL
                DO UPDATE SET status = EXCLUDED.status,
                              marked_by = EXCLUDED.marked_by,
                              marked_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (student_id, section_id, batch_id, date, status, marked_by,
                  general_period))
        elif attendance_type == 'subject':
            cur.execute("""
                INSERT INTO Attendance
                  (student_id, section_id, batch_id, date, status, marked_by, marked_at,
                   attendance_type, subject_id, session_id)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, 'subject', %s, %s)
                ON CONFLICT (student_id, section_id, subject_id, date, session_id)
                WHERE subject_id IS NOT NULL
                DO UPDATE SET status = EXCLUDED.status,
                              marked_by = EXCLUDED.marked_by,
                              marked_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (student_id, section_id, batch_id, date, status, marked_by,
                  subject_id, session_id))
        else:
            cur.execute("""
                INSERT INTO Attendance
                  (student_id, section_id, batch_id, date, status, marked_by, marked_at,
                   attendance_type, lab_id, session_id)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, 'lab', %s, %s)
                ON CONFLICT (student_id, section_id, lab_id, date, session_id)
                WHERE lab_id IS NOT NULL
                DO UPDATE SET status = EXCLUDED.status,
                              marked_by = EXCLUDED.marked_by,
                              marked_at = CURRENT_TIMESTAMP
                RETURNING id
            """, (student_id, section_id, batch_id, date, status, marked_by,
                  lab_id, session_id))
        attendance_id = cur.fetchone()[0]
        conn.commit()
        return attendance_id
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def claim_pending_notifications(batch_size=25):
    """Atomically picks up to N queued notifications, flips them to 'sending'
    so a second worker can't grab the same row. Returns list of dicts."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        WITH locked AS (
            SELECT id FROM ParentNotifications
            WHERE status = 'queued' AND attempt_count < 5
            ORDER BY queued_at
            LIMIT %s
            FOR UPDATE SKIP LOCKED
        )
        UPDATE ParentNotifications p
        SET status = 'sending', last_attempt_at = NOW()
        FROM locked WHERE p.id = locked.id
        RETURNING p.id, p.channel, p.recipient, p.message_body, p.attempt_count
    """, (batch_size,))
    rows = cur.fetchall()
    conn.commit()
    cur.close(); conn.close()
    return [{'id': r[0], 'channel': r[1], 'recipient': r[2],
             'message_body': r[3], 'attempt_count': r[4]} for r in rows]


def mark_notification_sent(notification_id, provider, provider_msg_id):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        UPDATE ParentNotifications
        SET status='sent', sent_at=NOW(), provider=%s, provider_msg_id=%s,
            last_error=NULL
        WHERE id = %s
    """, (provider, provider_msg_id, notification_id))
    conn.commit(); cur.close(); conn.close()


def mark_notification_failed(notification_id, provider, error, permanent=False):
    """Bumps attempt_count and either returns to 'queued' (retryable) or
    flips to 'failed' (permanent OR retry limit reached)."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        UPDATE ParentNotifications
        SET status = CASE
                       WHEN %s OR attempt_count + 1 >= 5 THEN 'failed'
                       ELSE 'queued'
                     END,
            attempt_count = attempt_count + 1,
            provider = %s,
            last_error = %s,
            last_attempt_at = NOW()
        WHERE id = %s
        RETURNING status
    """, (permanent, provider, error[:500] if error else None, notification_id))
    cur.fetchone()
    conn.commit(); cur.close(); conn.close()


def retry_notification(notification_id):
    """Admin-initiated retry: resets a row to queued, attempt_count back to 0."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        UPDATE ParentNotifications
        SET status='queued', attempt_count=0, last_error=NULL, last_attempt_at=NULL
        WHERE id = %s AND status IN ('failed', 'suppressed')
    """, (notification_id,))
    ok = cur.rowcount > 0
    conn.commit(); cur.close(); conn.close()
    return ok


def list_notifications(status=None, student_id=None, limit=200):
    """Read-side query for the /admin/notifications log viewer."""
    conn = get_db_connection(); cur = conn.cursor()
    sql = """
        SELECT n.id, n.student_id, s.name AS student_name, s.student_code,
               n.attendance_id, n.channel, n.recipient, n.status,
               n.provider, n.attempt_count, n.last_error,
               n.queued_at, n.sent_at, n.last_attempt_at
        FROM ParentNotifications n
        JOIN Students s ON s.id = n.student_id
    """
    clauses, params = [], []
    if status:
        clauses.append("n.status = %s"); params.append(status)
    if student_id:
        clauses.append("n.student_id = %s"); params.append(student_id)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY n.queued_at DESC LIMIT %s"
    params.append(int(limit))
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    cols = ['id', 'student_id', 'student_name', 'student_code',
            'attendance_id', 'channel', 'recipient', 'status',
            'provider', 'attempt_count', 'last_error',
            'queued_at', 'sent_at', 'last_attempt_at']
    return [dict(zip(cols, r)) for r in rows]


def update_attendance_settings(*, edit_window_hours=None, allow_backdate_days=None,
                               notify_absent=None, notify_channels=None,
                               message_template=None, actor_id=None):
    """Updates the singleton AttendanceSettings row. Any None argument is
    left unchanged."""
    fields, params = [], []
    if edit_window_hours is not None:
        fields.append("edit_window_hours = %s"); params.append(int(edit_window_hours))
    if allow_backdate_days is not None:
        fields.append("allow_backdate_days = %s"); params.append(int(allow_backdate_days))
    if notify_absent is not None:
        fields.append("notify_absent = %s"); params.append(bool(notify_absent))
    if notify_channels is not None:
        fields.append("notify_channels = %s"); params.append(list(notify_channels))
    if message_template is not None:
        fields.append("message_template = %s"); params.append(str(message_template))
    if not fields:
        return False
    fields.append("updated_at = NOW()")
    if actor_id is not None:
        fields.append("updated_by = %s"); params.append(actor_id)
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute(f"UPDATE AttendanceSettings SET {', '.join(fields)} WHERE id = 1",
                    params)
        if actor_id is not None:
            _audit(cur, 'attendance_settings', 1, 'update',
                   after={'fields': [f.split(' ')[0] for f in fields]},
                   actor_id=actor_id)
        conn.commit()
        return True
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def get_student_notify_prefs(student_id):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT id, name, parent_phone, parent_email, notify_channels
        FROM Students WHERE id = %s
    """, (student_id,))
    r = cur.fetchone()
    cur.close(); conn.close()
    if not r:
        return None
    return {'id': r[0], 'name': r[1],
            'parent_phone': r[2], 'parent_email': r[3],
            'notify_channels': list(r[4]) if r[4] is not None else None}


def set_student_notify_prefs(student_id, *, parent_phone=None, parent_email=None,
                             notify_channels='__unset__', actor_id=None):
    """Updates notification fields on a Students row. parent_phone/parent_email
    accept '' to clear. notify_channels supports three states:
        None  → inherit org default
        []    → opt-out
        ['sms','email']  → explicit list
    The sentinel '__unset__' means 'leave as-is'."""
    fields, params = [], []
    if parent_phone is not None:
        fields.append("parent_phone = %s"); params.append(parent_phone or None)
    if parent_email is not None:
        fields.append("parent_email = %s"); params.append(parent_email or None)
    if notify_channels != '__unset__':
        fields.append("notify_channels = %s"); params.append(notify_channels)
    if not fields:
        return False
    conn = get_db_connection(); cur = conn.cursor()
    try:
        params.append(student_id)
        cur.execute(f"UPDATE Students SET {', '.join(fields)} WHERE id = %s", params)
        ok = cur.rowcount > 0
        if ok and actor_id is not None:
            _audit(cur, 'student_notify_prefs', student_id, 'update',
                   after={'notify_channels': notify_channels if notify_channels != '__unset__' else None},
                   actor_id=actor_id)
        conn.commit()
        return ok
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def enqueue_absent_notifications(attendance_id, settings=None):
    """For an absent attendance row, queue one ParentNotifications row per
    resolved channel. UNIQUE(attendance_id, channel) prevents duplicates if
    the mark gets re-saved. Returns the count queued (excluding suppressed)."""
    if settings is None:
        settings = get_attendance_settings()
    if not settings.get('notify_absent'):
        return 0

    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT a.status, a.date, a.attendance_type,
               s.id, s.name, s.parent_phone, s.parent_email, s.notify_channels,
               sec.full_code, sub.code, sub.name AS subject_name,
               lab.code AS lab_code, lab.name AS lab_name
        FROM Attendance a
        JOIN Students    s   ON s.id  = a.student_id
        JOIN Sections    sec ON sec.id = a.section_id
        LEFT JOIN Subjects sub ON sub.id = a.subject_id
        LEFT JOIN Labs     lab ON lab.id = a.lab_id
        WHERE a.id = %s
    """, (attendance_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row or row[0] != 'absent':
        return 0

    (_status, date, att_type, student_id, student_name,
     parent_phone, parent_email, notify_channels,
     section_code, subject_code, subject_name,
     lab_code, lab_name) = row

    # Per-student override > org default; empty array = opt-out
    if notify_channels is None:
        channels = list(settings.get('notify_channels') or [])
    else:
        channels = list(notify_channels)
    if not channels:
        return 0

    if att_type == 'subject' and subject_code:
        context = f"subject {subject_name} ({subject_code})"
    elif att_type == 'lab' and lab_code:
        context = f"lab {lab_name} ({lab_code})"
    else:
        context = f"section {section_code}"
    body = (settings.get('message_template') or
            'Your child {student_name} was marked absent on {date} for {context}.').format(
        student_name=student_name, date=date, context=context,
    )

    conn = get_db_connection(); cur = conn.cursor()
    queued = 0
    try:
        for ch in channels:
            if ch not in ('sms', 'whatsapp', 'email'):
                continue
            recipient = parent_phone if ch in ('sms', 'whatsapp') else parent_email
            if not recipient:
                cur.execute("""
                    INSERT INTO ParentNotifications
                      (student_id, attendance_id, channel, recipient, message_body,
                       status, last_error)
                    VALUES (%s, %s, %s, '', %s, 'suppressed', 'no_recipient')
                    ON CONFLICT (attendance_id, channel) DO NOTHING
                """, (student_id, attendance_id, ch, body))
                continue
            cur.execute("""
                INSERT INTO ParentNotifications
                  (student_id, attendance_id, channel, recipient, message_body)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (attendance_id, channel) DO NOTHING
            """, (student_id, attendance_id, ch, recipient, body))
            if cur.rowcount > 0:
                queued += 1
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()
    return queued


def bulk_mark_attendance(batch_id, date, status, marked_by, *,
                         attendance_type='general', general_period='morning',
                         subject_id=None, lab_id=None, session_id=None):
    """Marks every student in a batch with the same status — used by the
    'Mark all Present/Absent' bulk shortcuts."""
    section_id = get_section_id_for_batch(batch_id)
    for student in get_students(batch_id):
        mark_attendance(
            student_id=student.id, date=date, status=status, marked_by=marked_by,
            attendance_type=attendance_type, general_period=general_period,
            section_id=section_id, batch_id=batch_id,
            subject_id=subject_id, lab_id=lab_id, session_id=session_id,
        )


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


# ---- Attendance v3: Reports ----------------------------------------------

def _attendance_source(include_archive):
    """Returns the SQL fragment that stands in for the Attendance table.
    With archive included, both live and archived rows participate via
    UNION ALL — column order is preserved because AttendanceArchive was
    created with LIKE Attendance INCLUDING ALL."""
    if include_archive:
        return ("(SELECT * FROM Attendance "
                "UNION ALL SELECT * FROM AttendanceArchive)")
    return "Attendance"


def report_section_summary(section_id, from_date=None, to_date=None,
                          include_archive=False):
    """Per-student attendance totals + present% for a section over a window.
    Counts each Attendance row regardless of type (general+subject+lab)."""
    src = _attendance_source(include_archive)
    sql = f"""
        SELECT s.id, s.student_code, s.name,
               COALESCE(SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END), 0) AS present,
               COALESCE(SUM(CASE WHEN a.status='absent'  THEN 1 ELSE 0 END), 0) AS absent,
               COALESCE(SUM(CASE WHEN a.status='late'    THEN 1 ELSE 0 END), 0) AS late,
               COALESCE(SUM(CASE WHEN a.status='leave'   THEN 1 ELSE 0 END), 0) AS leave_count,
               COUNT(a.id) AS total,
               CASE WHEN COUNT(a.id) > 0 THEN
                   ROUND(100.0 * SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) / COUNT(a.id), 1)
               ELSE NULL END AS percentage
        FROM Students s
        LEFT JOIN {src} a ON a.student_id = s.id
          AND a.section_id = %s
          AND (%s::date IS NULL OR a.date >= %s::date)
          AND (%s::date IS NULL OR a.date <= %s::date)
        WHERE s.section_id = %s
        GROUP BY s.id, s.student_code, s.name
        ORDER BY s.name
    """
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(sql, (section_id, from_date, from_date, to_date, to_date, section_id))
    rows = cur.fetchall()
    cur.close(); conn.close()
    cols = ['id', 'student_code', 'name', 'present', 'absent', 'late',
            'leave', 'total', 'percentage']
    return [dict(zip(cols, r)) for r in rows]


def report_subject_summary(subject_id, from_date=None, to_date=None,
                           include_archive=False):
    """Per-student attendance for a specific subject across all sections
    in the subject's course-year."""
    src = _attendance_source(include_archive)
    sql = f"""
        SELECT s.id, s.student_code, s.name, sec.full_code,
               COALESCE(SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END), 0) AS present,
               COALESCE(SUM(CASE WHEN a.status='absent'  THEN 1 ELSE 0 END), 0) AS absent,
               COALESCE(SUM(CASE WHEN a.status='late'    THEN 1 ELSE 0 END), 0) AS late,
               COALESCE(SUM(CASE WHEN a.status='leave'   THEN 1 ELSE 0 END), 0) AS leave_count,
               COUNT(a.id) AS total,
               CASE WHEN COUNT(a.id) > 0 THEN
                   ROUND(100.0 * SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) / COUNT(a.id), 1)
               ELSE NULL END AS percentage
        FROM Students s
        JOIN Sections sec ON sec.id = s.section_id
        LEFT JOIN {src} a ON a.student_id = s.id AND a.subject_id = %s
          AND (%s::date IS NULL OR a.date >= %s::date)
          AND (%s::date IS NULL OR a.date <= %s::date)
        WHERE sec.course_year_id = (SELECT course_year_id FROM Subjects WHERE id = %s)
        GROUP BY s.id, s.student_code, s.name, sec.full_code
        ORDER BY sec.full_code, s.name
    """
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(sql, (subject_id, from_date, from_date, to_date, to_date, subject_id))
    rows = cur.fetchall()
    cur.close(); conn.close()
    cols = ['id', 'student_code', 'name', 'section', 'present', 'absent',
            'late', 'leave', 'total', 'percentage']
    return [dict(zip(cols, r)) for r in rows]


def report_daily_absentees(date, section_id=None, include_archive=False):
    """Who was marked absent on this date, with parent contact info for
    follow-up calls. Optionally narrow to a single section."""
    src = _attendance_source(include_archive)
    sql = f"""
        SELECT a.id, a.attendance_type, a.general_period,
               s.id AS student_id, s.student_code, s.name,
               s.parent_phone, s.parent_email,
               sec.full_code AS section_code,
               c.name AS course_name, cy.year_number,
               sub.code AS subject_code, sub.name AS subject_name,
               u.name AS marked_by_name, u.username AS marked_by_username,
               a.marked_at
        FROM {src} a
        JOIN Students    s   ON s.id = a.student_id
        JOIN Sections    sec ON sec.id = a.section_id
        JOIN CourseYears cy  ON cy.id = sec.course_year_id
        JOIN Courses     c   ON c.id = cy.course_id
        LEFT JOIN Subjects sub ON sub.id = a.subject_id
        LEFT JOIN Users    u   ON u.id = a.marked_by
        WHERE a.status = 'absent' AND a.date = %s::date
          AND (%s::int IS NULL OR a.section_id = %s::int)
        ORDER BY sec.full_code, s.name
    """
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(sql, (date, section_id, section_id))
    rows = cur.fetchall()
    cur.close(); conn.close()
    cols = ['id', 'type', 'period', 'student_id', 'student_code', 'name',
            'parent_phone', 'parent_email', 'section_code',
            'course_name', 'year_number', 'subject_code', 'subject_name',
            'marked_by_name', 'marked_by_username', 'marked_at']
    return [dict(zip(cols, r)) for r in rows]


def report_faculty_activity(faculty_id=None, from_date=None, to_date=None,
                            include_archive=False):
    """Per-day, per-type count of attendance marks by a faculty (or all
    faculty when faculty_id is None)."""
    src = _attendance_source(include_archive)
    sql = f"""
        SELECT u.id AS marked_by, u.name AS marked_by_name, u.username,
               a.date, a.attendance_type,
               COUNT(*) AS marks,
               SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END) AS present,
               SUM(CASE WHEN a.status='absent'  THEN 1 ELSE 0 END) AS absent
        FROM {src} a
        JOIN Users u ON u.id = a.marked_by
        WHERE (%s::int IS NULL OR a.marked_by = %s::int)
          AND (%s::date IS NULL OR a.date >= %s::date)
          AND (%s::date IS NULL OR a.date <= %s::date)
        GROUP BY u.id, u.name, u.username, a.date, a.attendance_type
        ORDER BY a.date DESC, u.name, a.attendance_type
    """
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(sql, (faculty_id, faculty_id, from_date, from_date, to_date, to_date))
    rows = cur.fetchall()
    cur.close(); conn.close()
    cols = ['marked_by', 'marked_by_name', 'username', 'date', 'type',
            'marks', 'present', 'absent']
    return [dict(zip(cols, r)) for r in rows]


# ---- Absentee letters: helpers + eligibility -----------------------------

def list_holidays(from_date=None, to_date=None):
    conn = get_db_connection(); cur = conn.cursor()
    sql = "SELECT id, date, name, notes FROM Holidays"
    params, clauses = [], []
    if from_date:
        clauses.append("date >= %s"); params.append(from_date)
    if to_date:
        clauses.append("date <= %s"); params.append(to_date)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY date"
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{'id': r[0], 'date': r[1], 'name': r[2], 'notes': r[3]} for r in rows]


def add_holiday(date, name, notes=None, actor_id=None):
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO Holidays (date, name, notes, created_by) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (date, name, notes, actor_id)
        )
        hid = cur.fetchone()[0]
        if actor_id is not None:
            _audit(cur, 'holiday', hid, 'create',
                   after={'date': str(date), 'name': name},
                   actor_id=actor_id)
        conn.commit()
        return hid
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def delete_holiday(holiday_id, actor_id=None):
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("DELETE FROM Holidays WHERE id = %s", (holiday_id,))
        deleted = cur.rowcount > 0
        if deleted and actor_id is not None:
            _audit(cur, 'holiday', holiday_id, 'delete', actor_id=actor_id)
        conn.commit()
        return deleted
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def _weekend_days_for_section(section_id):
    """Returns the set of weekday names that count as weekends for this
    section — falls back to org-wide AttendanceSettings.weekend_days when
    the section's CourseYear has no override."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT cy.weekend_days_override, s.weekend_days
        FROM Sections sec
        JOIN CourseYears cy ON cy.id = sec.course_year_id
        CROSS JOIN AttendanceSettings s
        WHERE sec.id = %s AND s.id = 1
    """, (section_id,))
    r = cur.fetchone()
    cur.close(); conn.close()
    if not r:
        return {'Sunday'}
    override, org = r
    return set(override) if override else set(org or [])


def find_continuous_absentees(section_id, *, min_consecutive=None,
                              lookback_days=None):
    """Per-student current consecutive-absent streak for a section,
    ending on the most recent class-day on or before today.

    Day rules:
      • Weekends (per section) and Holidays are SKIPPED (no count, no break).
      • A day where the section had ZERO general attendance marked is SKIPPED.
      • A day with at least one 'present' general mark BREAKS the streak.
      • A day with only 'absent' marks COUNTS toward the streak.
      • A class day where THIS student has no mark BREAKS the streak.

    Returns a list of dicts (one per student in the section) annotated with
    consecutive_days, absent_from, absent_to, auto_selected, last_letter."""
    from datetime import date as _d, timedelta
    settings = get_attendance_settings()
    threshold = min_consecutive if min_consecutive is not None else \
        max(1, int(_setting_value(settings, 'absentee_letter_threshold', 3)))
    window = lookback_days if lookback_days is not None else \
        max(7, int(_setting_value(settings, 'absentee_letter_lookback_days', 30)))

    weekend = _weekend_days_for_section(section_id)
    holidays = {h['date'] for h in
                list_holidays(_d.today() - timedelta(days=window + 30),
                              _d.today())}

    # One SQL pass: pull per-(student, date) presence flags AND the section's
    # class-day set, all within the lookback window.
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT a.student_id, a.date,
               MAX(CASE WHEN a.status='present' THEN 1 ELSE 0 END) AS has_present,
               MAX(CASE WHEN a.status='absent'  THEN 1 ELSE 0 END) AS has_absent
        FROM Attendance a
        WHERE a.section_id = %s
          AND a.attendance_type = 'general'
          AND a.date >= CURRENT_DATE - (%s || ' days')::interval
        GROUP BY a.student_id, a.date
    """, (section_id, window))
    rows = cur.fetchall()
    cur.close(); conn.close()

    # Map: (student_id, date) → ('present'|'absent'|'unmarked-but-day-had-class')
    student_day = {}
    class_days = set()
    for sid, d, hp, ha in rows:
        class_days.add(d)
        if hp:
            student_day[(sid, d)] = 'present'
        elif ha:
            student_day[(sid, d)] = 'absent'
        else:
            student_day[(sid, d)] = 'unmarked'

    # Pre-build the ordered class-day walk (most-recent first)
    today = _d.today()
    walk = []
    d = today
    days_walked = 0
    while days_walked < window:
        if d.strftime('%A') in weekend or d in holidays:
            d -= timedelta(days=1); continue
        if d in class_days:
            walk.append(d)
        d -= timedelta(days=1); days_walked += 1
    # walk[0] = most recent class-day

    students = get_students_in_section(section_id)
    # Last letter per student (most recent only)
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT ON (student_id)
               student_id, id, generated_at, absent_from, absent_to, consecutive_days
        FROM AbsenteeLetters
        WHERE section_id = %s
          AND revoked_at IS NULL
        ORDER BY student_id, generated_at DESC
    """, (section_id,))
    last_letter_rows = cur.fetchall()
    cur.close(); conn.close()
    last_by_student = {r[0]: {
        'id': r[1], 'generated_at': r[2],
        'absent_from': r[3], 'absent_to': r[4],
        'consecutive_days': r[5],
    } for r in last_letter_rows}

    out = []
    for stu in students:
        streak = 0
        absent_from = absent_to = None
        for cd in walk:
            status = student_day.get((stu.id, cd))
            if status == 'present':
                break
            if status == 'absent':
                if absent_to is None:
                    absent_to = cd
                absent_from = cd
                streak += 1
            else:
                # student has no mark on a class day → ambiguous → break
                break
        if streak == 0:
            continue   # not absent at all in the window
        out.append({
            'student': stu,
            'consecutive_days': streak,
            'absent_from': absent_from,
            'absent_to': absent_to,
            'auto_selected': streak >= threshold,
            'last_letter': last_by_student.get(stu.id),
            'has_address': bool(stu.address),
            'has_parent': bool(stu.parent_name),
        })
    # Sort by streak desc so the longest absences float to the top
    out.sort(key=lambda r: r['consecutive_days'], reverse=True)
    return {
        'threshold': threshold,
        'lookback_days': window,
        'weekend_days': sorted(weekend),
        'candidates': out,
    }


def _setting_value(settings, key, default):
    """Tiny helper because get_attendance_settings() doesn't yet include
    the new keys until the next read. Kept loose for backward compat."""
    val = settings.get(key) if isinstance(settings, dict) else None
    return val if val is not None else default


def compute_monthly_summary(student_id, section_id, year=None, through_month=None):
    """Calendar-year per-month absence summary, from January through the
    requested month. Each row carries:
      - month (e.g. 'JANUARY')
      - absent_days (days the student was marked absent and not present)
      - month_pct (absent_days / class_days_that_month * 100)
      - cumulative_pct (running cumulative through this month)
    Months with no class days are skipped.

    Defaults: year = current year, through_month = current month."""
    from datetime import date as _d, datetime as _dt
    today = _d.today()
    year = year or today.year
    if through_month is None:
        end_month = today.month if today.year == year else 12
    else:
        end_month = max(1, min(12, int(through_month)))

    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        WITH class_days AS (
            SELECT DISTINCT date FROM Attendance
            WHERE section_id = %s AND attendance_type = 'general'
              AND EXTRACT(YEAR FROM date) = %s
        ),
        per_day AS (
            SELECT date,
                   MAX(CASE WHEN status='present' THEN 1 ELSE 0 END) AS has_present,
                   MAX(CASE WHEN status='absent'  THEN 1 ELSE 0 END) AS has_absent
            FROM Attendance
            WHERE student_id = %s AND section_id = %s
              AND attendance_type = 'general'
              AND EXTRACT(YEAR FROM date) = %s
            GROUP BY date
        )
        SELECT EXTRACT(MONTH FROM cd.date)::int AS m,
               COUNT(DISTINCT cd.date) AS class_days,
               COUNT(DISTINCT pd.date)
                 FILTER (WHERE pd.has_absent = 1 AND pd.has_present = 0) AS absent_days
        FROM class_days cd
        LEFT JOIN per_day pd ON pd.date = cd.date
        GROUP BY m
        ORDER BY m
    """, (section_id, year, student_id, section_id, year))
    raw = cur.fetchall()
    cur.close(); conn.close()

    by_month = {r[0]: (r[1], r[2]) for r in raw}
    out = []
    cum_class = 0
    cum_absent = 0
    for m in range(1, end_month + 1):
        cd, ad = by_month.get(m, (0, 0))
        cum_class += cd
        cum_absent += ad
        if cd == 0:
            continue
        month_pct = (100.0 * ad / cd) if cd else 0.0
        cum_pct = (100.0 * cum_absent / cum_class) if cum_class else 0.0
        out.append({
            'month': _dt(year, m, 1).strftime('%B').upper(),
            'absent_days': ad,
            'class_days': cd,
            'month_pct': round(month_pct, 2),
            'cumulative_pct': round(cum_pct, 2),
        })
    return out


def list_letter_templates():
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT id, name, is_default, subject_line, is_active, updated_at
        FROM AbsenteeLetterTemplates ORDER BY is_default DESC, name
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{'id': r[0], 'name': r[1], 'is_default': r[2],
             'subject_line': r[3], 'is_active': r[4],
             'updated_at': r[5]} for r in rows]


def update_letter_template(template_id, *, name=None, subject_line=None,
                           body_html=None, is_active=None, is_default=None,
                           signature_blocks=None, actor_id=None):
    fields, params = [], []
    if name is not None:
        fields.append("name = %s"); params.append(name)
    if subject_line is not None:
        fields.append("subject_line = %s"); params.append(subject_line)
    if body_html is not None:
        fields.append("body_html = %s"); params.append(body_html)
    if is_active is not None:
        fields.append("is_active = %s"); params.append(bool(is_active))
    if signature_blocks is not None:
        fields.append("signature_blocks = %s"); params.append(list(signature_blocks))
    if not fields and is_default is None:
        return False
    conn = get_db_connection(); cur = conn.cursor()
    try:
        if is_default is True:
            # Clear any existing default (partial UNIQUE index enforces it)
            cur.execute("UPDATE AbsenteeLetterTemplates SET is_default = FALSE "
                        "WHERE is_default = TRUE")
            fields.append("is_default = TRUE")
        elif is_default is False:
            fields.append("is_default = FALSE")
        fields.append("updated_at = NOW()")
        if actor_id is not None:
            fields.append("updated_by = %s"); params.append(actor_id)
        params.append(template_id)
        cur.execute(f"UPDATE AbsenteeLetterTemplates SET {', '.join(fields)} "
                    f"WHERE id = %s", params)
        if actor_id is not None:
            _audit(cur, 'letter_template', template_id, 'update',
                   after={'fields': [f.split(' ')[0] for f in fields]},
                   actor_id=actor_id)
        conn.commit()
        return True
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def add_letter_template(name, subject_line, body_html,
                        signature_blocks=None, actor_id=None):
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO AbsenteeLetterTemplates
              (name, subject_line, body_html, signature_blocks, created_by, updated_by)
            VALUES (%s, %s, %s, COALESCE(%s, ARRAY['SECTION I/C','COURSE INCHARGE',
                                                   'VICE PRINCIPAL','PRINCIPAL']::TEXT[]),
                    %s, %s)
            RETURNING id
        """, (name, subject_line, body_html,
              signature_blocks, actor_id, actor_id))
        tid = cur.fetchone()[0]
        if actor_id is not None:
            _audit(cur, 'letter_template', tid, 'create',
                   after={'name': name}, actor_id=actor_id)
        conn.commit()
        return tid
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def get_letter_template(template_id=None):
    """Returns the requested template or the default if id is None."""
    conn = get_db_connection(); cur = conn.cursor()
    if template_id:
        cur.execute("""SELECT id, name, subject_line, body_html, letterhead_path,
                              signature_blocks, is_active
                       FROM AbsenteeLetterTemplates WHERE id = %s""",
                    (template_id,))
    else:
        cur.execute("""SELECT id, name, subject_line, body_html, letterhead_path,
                              signature_blocks, is_active
                       FROM AbsenteeLetterTemplates
                       WHERE is_default = TRUE AND is_active = TRUE
                       LIMIT 1""")
    r = cur.fetchone()
    cur.close(); conn.close()
    if not r:
        return None
    return {'id': r[0], 'name': r[1], 'subject_line': r[2], 'body_html': r[3],
            'letterhead_path': r[4], 'signature_blocks': list(r[5] or []),
            'is_active': r[6]}


def get_student_by_id(student_id):
    """Fetch a single Student tuple (for letter rendering)."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(
        f"SELECT {_STUDENT_COLS} FROM Students s WHERE s.id = %s",
        (student_id,)
    )
    r = cur.fetchone()
    cur.close(); conn.close()
    return _student_from_row(r) if r else None


def insert_absentee_letter_row(*, student_id, section_id, template_id,
                               consecutive_days, absent_from, absent_to,
                               pdf_path, student_snapshot, cumulative_pct,
                               letter_ref=None, sha256=None,
                               generated_by=None):
    """Persists one AbsenteeLetters row + an audit entry. Returns the id."""
    import json as _json
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO AbsenteeLetters
              (student_id, section_id, template_id, consecutive_days,
               absent_from, absent_to, letter_ref, pdf_path, sha256,
               student_snapshot, cumulative_pct, generated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s, %s)
            RETURNING id
        """, (student_id, section_id, template_id, consecutive_days,
              absent_from, absent_to, letter_ref, pdf_path, sha256,
              _json.dumps(student_snapshot), cumulative_pct, generated_by))
        lid = cur.fetchone()[0]
        if generated_by is not None:
            _audit(cur, 'absentee_letter', lid, 'create',
                   after={'student_id': student_id, 'consecutive_days': consecutive_days,
                          'absent_from': str(absent_from), 'absent_to': str(absent_to)},
                   actor_id=generated_by)
        conn.commit()
        return lid
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def revoke_absentee_letter(letter_id, actor_id, reason=None):
    """Soft-revoke. The PDF stays on disk; the row is flagged."""
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE AbsenteeLetters
            SET revoked_at = NOW(), revoked_by = %s, revoked_reason = %s
            WHERE id = %s AND revoked_at IS NULL
        """, (actor_id, reason, letter_id))
        ok = cur.rowcount > 0
        if ok:
            _audit(cur, 'absentee_letter', letter_id, 'revoke',
                   after={'reason': reason}, actor_id=actor_id)
        conn.commit()
        return ok
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def list_absentee_letters(section_id=None, student_id=None,
                          from_date=None, to_date=None,
                          include_revoked=True, limit=200):
    """History query for the admin /admin/letters page."""
    conn = get_db_connection(); cur = conn.cursor()
    sql = """
        SELECT l.id, l.student_id, s.name AS student_name, s.student_code,
               l.section_id, sec.full_code AS section_code,
               l.consecutive_days, l.absent_from, l.absent_to, l.letter_ref,
               l.pdf_path, l.generated_at, l.generated_by,
               u.name AS generated_by_name, u.username,
               l.revoked_at, l.revoked_reason
        FROM AbsenteeLetters l
        JOIN Students s   ON s.id = l.student_id
        JOIN Sections sec ON sec.id = l.section_id
        LEFT JOIN Users u ON u.id = l.generated_by
    """
    clauses, params = [], []
    if section_id:
        clauses.append("l.section_id = %s"); params.append(section_id)
    if student_id:
        clauses.append("l.student_id = %s"); params.append(student_id)
    if from_date:
        clauses.append("l.generated_at >= %s"); params.append(from_date)
    if to_date:
        clauses.append("l.generated_at <= %s"); params.append(to_date)
    if not include_revoked:
        clauses.append("l.revoked_at IS NULL")
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY l.generated_at DESC LIMIT %s"
    params.append(int(limit))
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    cols = ['id', 'student_id', 'student_name', 'student_code',
            'section_id', 'section_code',
            'consecutive_days', 'absent_from', 'absent_to', 'letter_ref',
            'pdf_path', 'generated_at', 'generated_by',
            'generated_by_name', 'username',
            'revoked_at', 'revoked_reason']
    return [dict(zip(cols, r)) for r in rows]


def can_generate_absentee_letter(user_id, role, section_id):
    """Same gate as 'general' attendance — section incharge or admin only."""
    if role == 'admin':
        return True, None
    if role != 'faculty':
        return False, 'Not a staff account'
    if is_section_incharge(user_id, section_id):
        return True, None
    return False, 'You are not the incharge of this section'


def archive_old_attendance(cutoff_days=730, batch_size=10000):
    """Moves Attendance rows older than cutoff_days into AttendanceArchive,
    then cascades the related ParentNotifications archive (only sent/failed/
    suppressed rows — never archives queued/sending ones). Returns the count
    of attendance rows moved."""
    from datetime import date as _d, timedelta
    cutoff = _d.today() - timedelta(days=cutoff_days)
    conn = get_db_connection(); cur = conn.cursor()
    try:
        # 1. Archive related notifications first (FK cascades fire on the
        # Attendance delete, but we want to preserve the audit trail).
        cur.execute("""
            WITH moved AS (
                DELETE FROM ParentNotifications n
                USING Attendance a
                WHERE n.attendance_id = a.id
                  AND a.date < %s
                  AND n.status IN ('sent', 'failed', 'suppressed')
                RETURNING n.*
            )
            INSERT INTO ParentNotificationsArchive
            SELECT * FROM moved
        """, (cutoff,))
        notif_moved = cur.rowcount
        # 2. Archive the attendance rows themselves. For very large tables
        # this should be batched via ctid windows; for current volume we run
        # it in a single statement.
        cur.execute("""
            WITH moved AS (
                DELETE FROM Attendance
                WHERE date < %s
                RETURNING *
            )
            INSERT INTO AttendanceArchive SELECT * FROM moved
        """, (cutoff,))
        moved = cur.rowcount
        conn.commit()
        return {'attendance_rows_moved': moved, 'notification_rows_moved': notif_moved,
                'cutoff_date': cutoff.isoformat()}
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


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


# =============================================================================
# Course Management — master data CRUD
# =============================================================================

import json as _json


def _audit(cursor, entity, entity_id, action, before=None, after=None, actor_id=None):
    """Write a single audit row using the caller's cursor so it joins the
    same transaction as the operation being audited."""
    cursor.execute(
        "INSERT INTO AuditLog (entity, entity_id, action, actor_id, "
        "before_json, after_json) "
        "VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb)",
        (entity, entity_id, action, actor_id,
         _json.dumps(before) if before is not None else None,
         _json.dumps(after)  if after  is not None else None)
    )


def list_audit_log(entity=None, entity_id=None, action=None, limit=200):
    """Reads recent AuditLog rows, joining actor name. Filters are AND-ed.
    Returns a list of dicts ready for templating."""
    conn = get_db_connection(); cur = conn.cursor()
    sql = """
        SELECT a.id, a.entity, a.entity_id, a.action,
               a.actor_id, COALESCE(u.name, u.username, '—') AS actor_name,
               a.before_json, a.after_json, a.created_at
        FROM AuditLog a
        LEFT JOIN Users u ON u.id = a.actor_id
    """
    clauses, params = [], []
    if entity:
        clauses.append("a.entity = %s"); params.append(entity)
    if entity_id is not None:
        clauses.append("a.entity_id = %s"); params.append(entity_id)
    if action:
        clauses.append("a.action = %s"); params.append(action)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY a.created_at DESC, a.id DESC LIMIT %s"
    params.append(int(limit))
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [{
        'id':         r[0],
        'entity':     r[1],
        'entity_id':  r[2],
        'action':     r[3],
        'actor_id':   r[4],
        'actor_name': r[5],
        'before':     r[6],
        'after':      r[7],
        'created_at': r[8],
    } for r in rows]


def list_audit_entities():
    """Distinct entity types currently in the audit log — used to populate
    the filter dropdown on the viewer page."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT DISTINCT entity FROM AuditLog ORDER BY entity")
    rows = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows


# ---- Courses ---------------------------------------------------------------

def _course_from_row(r):
    return Course(id=r[0], code=r[1], name=r[2], is_active=r[3])


def list_courses(active_only=False):
    conn = get_db_connection(); cur = conn.cursor()
    sql = "SELECT id, code, name, is_active FROM Courses"
    if active_only:
        sql += " WHERE is_active = TRUE"
    sql += " ORDER BY name"
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [_course_from_row(r) for r in rows]


def get_course(course_id):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id, code, name, is_active FROM Courses WHERE id = %s",
                (course_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return _course_from_row(row) if row else None


def add_course(code, name, actor_id=None):
    code = (code or '').strip().upper()
    name = (name or '').strip()
    if not (code and name):
        raise ValueError("code and name are required")
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO Courses (code, name, created_by) "
            "VALUES (%s, %s, %s) RETURNING id",
            (code, name, actor_id)
        )
        cid = cur.fetchone()[0]
        _audit(cur, 'course', cid, 'create',
               after={'code': code, 'name': name}, actor_id=actor_id)
        conn.commit()
        return cid
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def update_course(course_id, name=None, is_active=None, actor_id=None):
    fields, params = [], []
    if name is not None:
        fields.append("name = %s"); params.append(name.strip())
    if is_active is not None:
        fields.append("is_active = %s"); params.append(bool(is_active))
    if not fields:
        return False
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT id, code, name, is_active FROM Courses WHERE id = %s",
                    (course_id,))
        before = cur.fetchone()
        if not before:
            return False
        params.append(course_id)
        cur.execute(f"UPDATE Courses SET {', '.join(fields)} WHERE id = %s", params)
        _audit(cur, 'course', course_id, 'update',
               before={'name': before[2], 'is_active': before[3]},
               after={'name':  name      if name      is not None else before[2],
                      'is_active': bool(is_active) if is_active is not None else before[3]},
               actor_id=actor_id)
        conn.commit()
        return True
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def delete_course(course_id, actor_id=None):
    """Soft-delete only. Hard-delete would cascade CourseYears and could
    orphan downstream attendance rows."""
    return update_course(course_id, is_active=False, actor_id=actor_id)


# ---- CourseYears ----------------------------------------------------------

def _course_year_from_row(r):
    return CourseYear(id=r[0], course_id=r[1], year_number=r[2])


def list_course_years(course_id):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id, course_id, year_number FROM CourseYears "
                "WHERE course_id = %s ORDER BY year_number", (course_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [_course_year_from_row(r) for r in rows]


def get_course_year(course_year_id):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id, course_id, year_number FROM CourseYears WHERE id = %s",
                (course_year_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return _course_year_from_row(row) if row else None


def add_course_year(course_id, year_number, actor_id=None):
    year_number = int(year_number)
    if not (1 <= year_number <= 6):
        raise ValueError("year_number must be between 1 and 6")
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO CourseYears (course_id, year_number) "
            "VALUES (%s, %s) RETURNING id",
            (course_id, year_number)
        )
        cyid = cur.fetchone()[0]
        _audit(cur, 'course_year', cyid, 'create',
               after={'course_id': course_id, 'year_number': year_number},
               actor_id=actor_id)
        conn.commit()
        return cyid
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def delete_course_year(course_year_id, actor_id=None):
    """Hard-delete. DB will RESTRICT if any Sections reference this row."""
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT id, course_id, year_number FROM CourseYears "
                    "WHERE id = %s", (course_year_id,))
        before = cur.fetchone()
        if not before:
            return False
        cur.execute("DELETE FROM CourseYears WHERE id = %s", (course_year_id,))
        _audit(cur, 'course_year', course_year_id, 'delete',
               before={'course_id': before[1], 'year_number': before[2]},
               actor_id=actor_id)
        conn.commit()
        return True
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


# ---- Sections -------------------------------------------------------------

_SECTION_COLS = "id, course_year_id, section_code, full_code, incharge_id, is_active"


def _section_from_row(r):
    return Section(id=r[0], course_year_id=r[1], section_code=r[2],
                   full_code=r[3], incharge_id=r[4], is_active=r[5])


def list_sections(course_year_id=None, active_only=False):
    conn = get_db_connection(); cur = conn.cursor()
    sql = f"SELECT {_SECTION_COLS} FROM Sections"
    clauses, params = [], []
    if course_year_id is not None:
        clauses.append("course_year_id = %s"); params.append(course_year_id)
    if active_only:
        clauses.append("is_active = TRUE")
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY full_code"
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [_section_from_row(r) for r in rows]


def get_section(section_id):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(f"SELECT {_SECTION_COLS} FROM Sections WHERE id = %s", (section_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return _section_from_row(row) if row else None


def get_section_by_full_code(full_code):
    if not full_code:
        return None
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute(f"SELECT {_SECTION_COLS} FROM Sections WHERE full_code = %s",
                (full_code.strip().upper(),))
    row = cur.fetchone()
    cur.close(); conn.close()
    return _section_from_row(row) if row else None


def add_section(course_year_id, section_code, full_code=None, actor_id=None):
    section_code = (section_code or '').strip().upper()
    if not section_code:
        raise ValueError("section_code is required")
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute(
            "SELECT c.name, c.code, cy.year_number FROM CourseYears cy "
            "JOIN Courses c ON c.id = cy.course_id WHERE cy.id = %s",
            (course_year_id,)
        )
        meta = cur.fetchone()
        if not meta:
            raise ValueError(f"course_year_id {course_year_id} not found")
        course_name, course_code, year_num = meta
        if not full_code:
            full_code = f"{course_code}{year_num}{section_code}"
        full_code = full_code.strip().upper()
        cur.execute(
            "INSERT INTO Sections (course_year_id, section_code, full_code) "
            "VALUES (%s, %s, %s) RETURNING id",
            (course_year_id, section_code, full_code)
        )
        sid = cur.fetchone()[0]
        # Mirror into legacy Batches so old dropdowns (attendance reports etc.)
        # pick up the new section without waiting for a roster sync.
        cur.execute(
            "SELECT id FROM Batches WHERE course = %s AND year = %s AND section = %s",
            (course_name, year_num, section_code)
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO Batches (name, faculty_id, course, year, section) "
                "VALUES (%s, NULL, %s, %s, %s)",
                (f"{course_name} - Year {year_num} - {section_code}",
                 course_name, year_num, section_code)
            )
        _audit(cur, 'section', sid, 'create',
               after={'course_year_id': course_year_id,
                      'section_code': section_code,
                      'full_code': full_code},
               actor_id=actor_id)
        conn.commit()
        return sid
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def update_section(section_id, section_code=None, full_code=None,
                   is_active=None, actor_id=None):
    fields, params = [], []
    if section_code is not None:
        fields.append("section_code = %s"); params.append(section_code.strip().upper())
    if full_code is not None:
        fields.append("full_code = %s"); params.append(full_code.strip().upper())
    if is_active is not None:
        fields.append("is_active = %s"); params.append(bool(is_active))
    if not fields:
        return False
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute(f"SELECT {_SECTION_COLS} FROM Sections WHERE id = %s",
                    (section_id,))
        before = cur.fetchone()
        if not before:
            return False
        params.append(section_id)
        cur.execute(f"UPDATE Sections SET {', '.join(fields)} WHERE id = %s", params)
        _audit(cur, 'section', section_id, 'update',
               before={'section_code': before[2], 'full_code': before[3],
                       'is_active': before[5]},
               after={
                   'section_code': section_code if section_code is not None else before[2],
                   'full_code':    full_code    if full_code    is not None else before[3],
                   'is_active':    bool(is_active) if is_active is not None else before[5],
               },
               actor_id=actor_id)
        conn.commit()
        return True
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def delete_section(section_id, actor_id=None):
    """Soft-delete — never hard-delete because attendance may reference it."""
    return update_section(section_id, is_active=False, actor_id=actor_id)


def get_course_tree(active_only=False):
    """Single-query nested view: [{course, years:[{year, sections:[...]}]}]
    Driving structure for the admin course-tree page."""
    conn = get_db_connection(); cur = conn.cursor()
    sql = """
        SELECT c.id, c.code, c.name, c.is_active,
               cy.id, cy.year_number,
               s.id, s.section_code, s.full_code, s.incharge_id, s.is_active,
               u.name AS incharge_name,
               (SELECT COUNT(*) FROM Students st WHERE st.section_id = s.id) AS students
        FROM Courses c
        LEFT JOIN CourseYears cy ON cy.course_id = c.id
        LEFT JOIN Sections    s  ON s.course_year_id = cy.id
        LEFT JOIN Users       u  ON u.id = s.incharge_id
    """
    if active_only:
        sql += " WHERE c.is_active = TRUE"
    sql += " ORDER BY c.name, cy.year_number, s.section_code"
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close(); conn.close()

    tree = {}
    for (cid, ccode, cname, cactive, cyid, cyyr, sid, sccode, sfull,
         sinch, sactive, inch_name, scount) in rows:
        course = tree.setdefault(cid, {
            'id': cid, 'code': ccode, 'name': cname,
            'is_active': cactive, 'years': {},
        })
        if cyid is None:
            continue
        year = course['years'].setdefault(cyid, {
            'id': cyid, 'year_number': cyyr, 'sections': [],
        })
        if sid is None:
            continue
        year['sections'].append({
            'id': sid, 'section_code': sccode, 'full_code': sfull,
            'incharge_id': sinch, 'incharge_name': inch_name,
            'is_active': sactive, 'student_count': scount or 0,
        })

    result = []
    for c in tree.values():
        c['years'] = sorted(c['years'].values(), key=lambda y: y['year_number'])
        result.append(c)
    return sorted(result, key=lambda c: c['name'])


# ---- Subjects -------------------------------------------------------------

def _subject_from_row(r):
    return Subject(id=r[0], course_year_id=r[1], code=r[2], name=r[3],
                   credits=r[4], is_active=r[5])


def list_subjects(course_year_id, active_only=False):
    conn = get_db_connection(); cur = conn.cursor()
    sql = ("SELECT id, course_year_id, code, name, credits, is_active "
           "FROM Subjects WHERE course_year_id = %s")
    if active_only:
        sql += " AND is_active = TRUE"
    sql += " ORDER BY name"
    cur.execute(sql, (course_year_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [_subject_from_row(r) for r in rows]


def add_subject(course_year_id, code, name, credits=None, actor_id=None):
    code = (code or '').strip().upper()
    name = (name or '').strip()
    if not (code and name):
        raise ValueError("code and name are required")
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO Subjects (course_year_id, code, name, credits) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (course_year_id, code, name, credits)
        )
        sid = cur.fetchone()[0]
        _audit(cur, 'subject', sid, 'create',
               after={'course_year_id': course_year_id, 'code': code,
                      'name': name, 'credits': credits},
               actor_id=actor_id)
        conn.commit()
        return sid
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def update_subject(subject_id, name=None, credits=None, is_active=None, actor_id=None):
    fields, params = [], []
    if name is not None:
        fields.append("name = %s"); params.append(name.strip())
    if credits is not None:
        fields.append("credits = %s"); params.append(credits)
    if is_active is not None:
        fields.append("is_active = %s"); params.append(bool(is_active))
    if not fields:
        return False
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT id, code, name, credits, is_active FROM Subjects "
                    "WHERE id = %s", (subject_id,))
        before = cur.fetchone()
        if not before:
            return False
        params.append(subject_id)
        cur.execute(f"UPDATE Subjects SET {', '.join(fields)} WHERE id = %s", params)
        _audit(cur, 'subject', subject_id, 'update',
               before={'name': before[2], 'credits': before[3], 'is_active': before[4]},
               after={'name':    name    if name    is not None else before[2],
                      'credits': credits if credits is not None else before[3],
                      'is_active': bool(is_active) if is_active is not None else before[4]},
               actor_id=actor_id)
        conn.commit()
        return True
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def delete_subject(subject_id, actor_id=None):
    return update_subject(subject_id, is_active=False, actor_id=actor_id)


def parse_subjects_xlsx(file_stream):
    from openpyxl import load_workbook
    wb = load_workbook(file_stream, data_only=True, read_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        return []
    expected = ['code', 'name', 'credits']
    normalized = [str(h).strip().lower() if h else '' for h in header]
    for req in ('code', 'name'):
        if req not in normalized:
            raise ValueError(f"Missing required column: {req}")
    idx = {c: normalized.index(c) if c in normalized else None for c in expected}
    out = []
    for row in rows:
        if row is None or all(v is None or str(v).strip() == '' for v in row):
            continue
        out.append({c: row[i] if i is not None and i < len(row) else None
                    for c, i in idx.items()})
    return out


def bulk_add_subjects(course_year_id, records, actor_id=None):
    """Returns (added, skipped, errors). 'skipped' counts duplicate codes."""
    existing = {s.code for s in list_subjects(course_year_id)}
    added, skipped, errors = 0, 0, []
    for idx, rec in enumerate(records, start=2):
        try:
            code = str(rec.get('code') or '').strip().upper()
            name = str(rec.get('name') or '').strip()
            credits_raw = rec.get('credits')
            credits = int(credits_raw) if credits_raw not in (None, '') else None
            if not (code and name):
                errors.append(f"Row {idx}: code and name are required")
                continue
            if code in existing:
                skipped += 1
                continue
            add_subject(course_year_id, code, name, credits=credits, actor_id=actor_id)
            existing.add(code)
            added += 1
        except Exception as exc:
            errors.append(f"Row {idx}: {exc}")
    return added, skipped, errors





# ---- Labs (mirror of Subjects, no credits column) -------------------------

def _lab_from_row(r):
    return Lab(id=r[0], course_year_id=r[1], code=r[2], name=r[3], is_active=r[4])


def list_labs(course_year_id, active_only=False):
    conn = get_db_connection(); cur = conn.cursor()
    sql = ("SELECT id, course_year_id, code, name, is_active "
           "FROM Labs WHERE course_year_id = %s")
    if active_only:
        sql += " AND is_active = TRUE"
    sql += " ORDER BY name"
    cur.execute(sql, (course_year_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [_lab_from_row(r) for r in rows]


def add_lab(course_year_id, code, name, actor_id=None):
    code = (code or '').strip().upper()
    name = (name or '').strip()
    if not (code and name):
        raise ValueError("code and name are required")
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO Labs (course_year_id, code, name) "
            "VALUES (%s, %s, %s) RETURNING id",
            (course_year_id, code, name)
        )
        lid = cur.fetchone()[0]
        _audit(cur, 'lab', lid, 'create',
               after={'course_year_id': course_year_id, 'code': code, 'name': name},
               actor_id=actor_id)
        conn.commit()
        return lid
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def update_lab(lab_id, name=None, is_active=None, actor_id=None):
    fields, params = [], []
    if name is not None:
        fields.append("name = %s"); params.append(name.strip())
    if is_active is not None:
        fields.append("is_active = %s"); params.append(bool(is_active))
    if not fields:
        return False
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT id, code, name, is_active FROM Labs WHERE id = %s",
                    (lab_id,))
        before = cur.fetchone()
        if not before:
            return False
        params.append(lab_id)
        cur.execute(f"UPDATE Labs SET {', '.join(fields)} WHERE id = %s", params)
        _audit(cur, 'lab', lab_id, 'update',
               before={'name': before[2], 'is_active': before[3]},
               after={'name':      name      if name      is not None else before[2],
                      'is_active': bool(is_active) if is_active is not None else before[3]},
               actor_id=actor_id)
        conn.commit()
        return True
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def delete_lab(lab_id, actor_id=None):
    return update_lab(lab_id, is_active=False, actor_id=actor_id)


def parse_labs_xlsx(file_stream):
    from openpyxl import load_workbook
    wb = load_workbook(file_stream, data_only=True, read_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        return []
    expected = ['code', 'name']
    normalized = [str(h).strip().lower() if h else '' for h in header]
    for req in expected:
        if req not in normalized:
            raise ValueError(f"Missing required column: {req}")
    idx = {c: normalized.index(c) for c in expected}
    out = []
    for row in rows:
        if row is None or all(v is None or str(v).strip() == '' for v in row):
            continue
        out.append({c: row[i] if i < len(row) else None for c, i in idx.items()})
    return out


def bulk_add_labs(course_year_id, records, actor_id=None):
    existing = {l.code for l in list_labs(course_year_id)}
    added, skipped, errors = 0, 0, []
    for idx, rec in enumerate(records, start=2):
        try:
            code = str(rec.get('code') or '').strip().upper()
            name = str(rec.get('name') or '').strip()
            if not (code and name):
                errors.append(f"Row {idx}: code and name are required")
                continue
            if code in existing:
                skipped += 1
                continue
            add_lab(course_year_id, code, name, actor_id=actor_id)
            existing.add(code)
            added += 1
        except Exception as exc:
            errors.append(f"Row {idx}: {exc}")
    return added, skipped, errors


# ---- StaffSectionMap ------------------------------------------------------

def get_staff_for_section(section_id):
    """Returns [(user_id, name, is_incharge), ...] for a section."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.name, u.username, ssm.is_incharge
        FROM StaffSectionMap ssm
        JOIN Users u ON u.id = ssm.user_id
        WHERE ssm.section_id = %s
        ORDER BY ssm.is_incharge DESC, u.name
    """, (section_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def get_sections_for_staff(user_id):
    """Returns [(section_id, full_code, is_incharge), ...] for a user."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT s.id, s.full_code, ssm.is_incharge
        FROM StaffSectionMap ssm
        JOIN Sections s ON s.id = ssm.section_id
        WHERE ssm.user_id = %s
        ORDER BY s.full_code
    """, (user_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def set_section_incharge(section_id, user_id, actor_id=None):
    """Sets the single incharge for a section. user_id=None clears it.
    If user_id wasn't assigned to the section, they are auto-assigned."""
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT incharge_id FROM Sections WHERE id = %s", (section_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("section not found")
        prev = row[0]
        cur.execute(
            "UPDATE StaffSectionMap SET is_incharge = FALSE "
            "WHERE section_id = %s AND is_incharge = TRUE", (section_id,)
        )
        if user_id is not None:
            cur.execute(
                "INSERT INTO StaffSectionMap (user_id, section_id, is_incharge, assigned_by) "
                "VALUES (%s, %s, TRUE, %s) "
                "ON CONFLICT (user_id, section_id) DO UPDATE "
                "SET is_incharge = TRUE, assigned_by = EXCLUDED.assigned_by",
                (user_id, section_id, actor_id)
            )
        cur.execute("UPDATE Sections SET incharge_id = %s WHERE id = %s",
                    (user_id, section_id))
        _audit(cur, 'section', section_id, 'set_incharge',
               before={'incharge_id': prev}, after={'incharge_id': user_id},
               actor_id=actor_id)
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def set_user_sections(user_id, assignments, actor_id=None):
    """Destructive-replace: deletes all of user_id's StaffSectionMap rows and
    inserts the new set. assignments = [{section_id, is_incharge}].
    For any section where is_incharge=True, the prior incharge (if any) is
    demoted. Sections where this user was previously the incharge but is now
    unassigned have their Sections.incharge_id cleared to NULL."""
    new_section_ids = {a['section_id'] for a in assignments}
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT section_id, is_incharge FROM StaffSectionMap "
                    "WHERE user_id = %s", (user_id,))
        before_rows = cur.fetchall()
        before = [{'section_id': r[0], 'is_incharge': r[1]} for r in before_rows]
        dropped_incharge = [r[0] for r in before_rows
                            if r[1] and r[0] not in new_section_ids]
        cur.execute("DELETE FROM StaffSectionMap WHERE user_id = %s", (user_id,))
        for sec_id in dropped_incharge:
            cur.execute("UPDATE Sections SET incharge_id = NULL WHERE id = %s",
                        (sec_id,))
        for a in assignments:
            sid = a['section_id']
            is_in = bool(a.get('is_incharge'))
            if is_in:
                cur.execute(
                    "UPDATE StaffSectionMap SET is_incharge = FALSE "
                    "WHERE section_id = %s AND is_incharge = TRUE", (sid,)
                )
            cur.execute(
                "INSERT INTO StaffSectionMap "
                "(user_id, section_id, is_incharge, assigned_by) "
                "VALUES (%s, %s, %s, %s)",
                (user_id, sid, is_in, actor_id)
            )
            if is_in:
                cur.execute("UPDATE Sections SET incharge_id = %s WHERE id = %s",
                            (user_id, sid))
        _audit(cur, 'staff_section_map', user_id, 'replace',
               before=before, after=assignments, actor_id=actor_id)
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


# ---- SubjectStaffMap & LabStaffMap (mirror of StaffSectionMap) -----------

def get_subjects_for_staff(user_id):
    """Returns [(subject_id, code, name, is_incharge), ...] for a user."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT s.id, s.code, s.name, m.is_incharge
        FROM SubjectStaffMap m
        JOIN Subjects s ON s.id = m.subject_id
        WHERE m.user_id = %s
        ORDER BY s.code
    """, (user_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def get_labs_for_staff(user_id):
    """Returns [(lab_id, code, name, is_incharge), ...] for a user."""
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT l.id, l.code, l.name, m.is_incharge
        FROM LabStaffMap m
        JOIN Labs l ON l.id = m.lab_id
        WHERE m.user_id = %s
        ORDER BY l.code
    """, (user_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def get_staff_for_subject(subject_id):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.name, u.username, m.is_incharge
        FROM SubjectStaffMap m
        JOIN Users u ON u.id = m.user_id
        WHERE m.subject_id = %s
        ORDER BY m.is_incharge DESC, u.name
    """, (subject_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def set_user_subjects(user_id, assignments, actor_id=None):
    """Same shape as set_user_sections, but for SubjectStaffMap."""
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT subject_id, is_incharge FROM SubjectStaffMap "
                    "WHERE user_id = %s", (user_id,))
        before = [{'subject_id': r[0], 'is_incharge': r[1]} for r in cur.fetchall()]
        cur.execute("DELETE FROM SubjectStaffMap WHERE user_id = %s", (user_id,))
        for a in assignments:
            sid = a['subject_id']
            is_in = bool(a.get('is_incharge'))
            if is_in:
                cur.execute(
                    "UPDATE SubjectStaffMap SET is_incharge = FALSE "
                    "WHERE subject_id = %s AND is_incharge = TRUE", (sid,)
                )
            cur.execute(
                "INSERT INTO SubjectStaffMap "
                "(user_id, subject_id, is_incharge, assigned_by) "
                "VALUES (%s, %s, %s, %s)",
                (user_id, sid, is_in, actor_id)
            )
        _audit(cur, 'subject_staff_map', user_id, 'replace',
               before=before, after=assignments, actor_id=actor_id)
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()


def get_staff_for_lab(lab_id):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.name, u.username, m.is_incharge
        FROM LabStaffMap m
        JOIN Users u ON u.id = m.user_id
        WHERE m.lab_id = %s
        ORDER BY m.is_incharge DESC, u.name
    """, (lab_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def set_user_labs(user_id, assignments, actor_id=None):
    """Same shape as set_user_sections, but for LabStaffMap."""
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT lab_id, is_incharge FROM LabStaffMap "
                    "WHERE user_id = %s", (user_id,))
        before = [{'lab_id': r[0], 'is_incharge': r[1]} for r in cur.fetchall()]
        cur.execute("DELETE FROM LabStaffMap WHERE user_id = %s", (user_id,))
        for a in assignments:
            lid = a['lab_id']
            is_in = bool(a.get('is_incharge'))
            if is_in:
                cur.execute(
                    "UPDATE LabStaffMap SET is_incharge = FALSE "
                    "WHERE lab_id = %s AND is_incharge = TRUE", (lid,)
                )
            cur.execute(
                "INSERT INTO LabStaffMap "
                "(user_id, lab_id, is_incharge, assigned_by) "
                "VALUES (%s, %s, %s, %s)",
                (user_id, lid, is_in, actor_id)
            )
        _audit(cur, 'lab_staff_map', user_id, 'replace',
               before=before, after=assignments, actor_id=actor_id)
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close(); conn.close()
