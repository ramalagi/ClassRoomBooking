# Room Booking System

A Python Flask web application for booking classrooms and meeting rooms.

## Setup

1. Install Python 3.x
3. Install PostgreSQL and create a database named `RoomBooking`.
4. Install dependencies: `pip install -r requirements.txt`
5. Set environment variables as needed:
   - `FLASK_SECRET_KEY`
   - `DATABASE_URL` = `postgres://user:password@host:5432/RoomBooking`
   - or use `PGHOST`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGPORT`
6. Initialize database: `python init_db.py`
7. Run the app: `python app.py`

## Login

Use the sample credentials:

- Admin: `admin` / `admin123`
- User: `user1` / `user123`

## Deployment

### Push to GitHub

1. Install Git locally.
2. Initialize the repo if needed:
   - `git init`
   - `git add .`
   - `git commit -m "Initial room booking app"`
3. Create a GitHub repository and add it as a remote:
   - `git remote add origin https://github.com/<your-username>/<repo-name>.git`
4. Push the code:
   - `git push -u origin main`

### Deploy to Render

1. Sign up at https://render.com and connect your GitHub account.
2. Push your repo to GitHub. Render detects `render.yaml` and can create services automatically.
3. In Render, create a new service by selecting your repository and branch.
4. Render will use `render.yaml` to configure the web service and PostgreSQL database.
5. Set the secret environment variable:
   - `FLASK_SECRET_KEY`

If `DATABASE_URL` is not automatically configured, add it manually with the Render database connection string.

### Automatic deployment setup

- `render.yaml` defines the Python web service and a managed PostgreSQL database.
- When you push changes to GitHub, Render automatically rebuilds and redeploys the app.
- The app now initializes the database schema and sample data on first startup if needed.

2. Create a new Web Service and select your repository.
3. Use the default Python environment.
4. Set the build command to `pip install -r requirements.txt`.
5. Set the start command to `python app.py`.
6. Add Render environment variables for `FLASK_SECRET_KEY`, `SQL_SERVER`, `SQL_DATABASE`, `SQL_TRUSTED_CONNECTION`, and optionally `SQL_USER` / `SQL_PASSWORD`.
7. Deploy the service.

> Note: Render must be able to reach your SQL Server instance. For public deployment, use a cloud-accessible SQL Server or use Render's managed database service if you migrate the app to another supported database.

## Features

- View room availability by date
- Book rooms for specific time slots
- Prevent double bookings
- Dashboard with color-coded availability

## Database Schema

- Rooms: id, name, type
- TimeSlots: id, day, period
- Bookings: id, staff_name, room_id, timeslot_id, date