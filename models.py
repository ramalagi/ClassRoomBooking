from db import get_db_connection
from collections import namedtuple

# Simple data classes for returned objects
Room = namedtuple('Room', ['id', 'name', 'type'])
TimeSlot = namedtuple('TimeSlot', ['id', 'day', 'period'])

def create_database():
    # PostgreSQL database creation is usually handled outside the app.
    # When using local PostgreSQL, ensure the RoomBooking database exists.
    return

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(100) NOT NULL,
            role VARCHAR(50) NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Rooms (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            type VARCHAR(50) NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS TimeSlots (
            id SERIAL PRIMARY KEY,
            day VARCHAR(20) NOT NULL,
            period VARCHAR(20) NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Bookings (
            id SERIAL PRIMARY KEY,
            user_id INT NOT NULL,
            room_id INT NOT NULL,
            timeslot_id INT NOT NULL,
            date DATE NOT NULL,
            FOREIGN KEY (user_id) REFERENCES Users(id),
            FOREIGN KEY (room_id) REFERENCES Rooms(id),
            FOREIGN KEY (timeslot_id) REFERENCES TimeSlots(id)
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
        ('admin', 'admin123', 'admin'),
        ('user1', 'user123', 'user'),
        ('user2', 'user123', 'user')
    ]
    cursor.executemany("INSERT INTO Users (username, password, role) VALUES (%s, %s, %s)", users)
    
    # Insert sample rooms
    rooms = [
        ('Classroom 101', 'classroom'),
        ('Classroom 102', 'classroom'),
        ('Meeting Room A', 'meeting_room'),
        ('Meeting Room B', 'meeting_room')
    ]
    cursor.executemany("INSERT INTO Rooms (name, type) VALUES (%s, %s)", rooms)
    
    # Insert time slots for one week (assuming Monday to Friday, hourly periods from 9am to 5pm)
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    periods = ['9:00-10:00', '10:00-11:00', '11:00-12:00', '12:00-13:00', '13:00-14:00', '14:00-15:00', '15:00-16:00', '16:00-17:00']
    
    timeslots = []
    for day in days:
        for period in periods:
            timeslots.append((day, period))
    
    cursor.executemany("INSERT INTO TimeSlots (day, period) VALUES (%s, %s)", timeslots)
    
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
    cursor.execute("SELECT id, username, role FROM Users WHERE username = %s AND password = %s", (username, password))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role FROM Users")
    users = cursor.fetchall()
    cursor.close()
    conn.close()
    return users

def add_user(username, password, role):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO Users (username, password, role) VALUES (%s, %s, %s)", (username, password, role))
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
    cursor.execute("DELETE FROM Users WHERE id = %s", (user_id,))
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
        return False  # Already booked
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO Bookings (user_id, room_id, timeslot_id, date)
        VALUES (%s, %s, %s, %s)
    """, (user_id, room_id, timeslot_id, date))
    conn.commit()
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