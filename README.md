# Hotel Booking — FastAPI + SQLAlchemy

Python FastAPI/SQLAlchemy server. The React/Redux frontend. FastAPI preserves `/api` URLs and frontend-facing `_id`, `isAdmin`, `checkInDate`, etc. JSON fields.

## Start on Ubuntu 24.04

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
cd hotel-book
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
# Edit .env and set a unique JWT_SECRET (at least 20 characters).
# The next command automatically loads .env because of python-dotenv.
npm run server
```

In another terminal:

```bash
cd hotel-book/frontend
npm ci
npm start
```

Frontend runs at `http://localhost:3000`; API runs at `http://127.0.0.1:5000`; API docs at `http://127.0.0.1:5000/docs`. Frontend's existing proxy forwards `/api` and `/uploads` to port 5000.

**Only the frontend requires npm.** Do not run `npm install` in the project root; the old Express backend and native `bcrypt@5.0.1` dependencies are removed.

## Database

By default, the SQLite database is always located at **`<project root>/hotel_booking.db`**, regardless of the working directory used to start the server or seed script. Relative SQLite paths in `DATABASE_URL` are resolved from the project root; absolute database URLs are left unchanged. Set `DATABASE_URL=postgresql+psycopg://...` for PostgreSQL. SQLAlchemy creates tables on startup. For ongoing production schema changes, introduce Alembic migrations. Existing MongoDB data is **not automatically migrated**.

## Seed a test user, an admin, and a room (local development)

A new database starts empty. From the **project root** (the same directory in which you start `npm run server`), after creating `.env` and installing `backend/requirements.txt`:

```bash
source .venv/bin/activate
python backend/seed_demo.py
```

You may also run `python seed_demo.py` from inside `backend/`; it will use the same root database. If an older run created `backend/hotel_booking.db` or a database in another directory, that is a separate SQLite file and is not used by the corrected default configuration.

The seed script prints the actual **Database:** URL before creating records. Verify that the server and seed use the same `DATABASE_URL` and `.env`. The script creates these local demo accounts (unless they already exist), makes the admin account an admin, and creates a sample `Demo King Room` owned by the admin:

| Role | Email | Password on first creation |
|---|---|---|
| Test user | `test@example.com` | `TestPass123!` |
| Admin | `admin@example.com` | `AdminPass123!` |

**Find the room ID:** The seed script prints `ROOM_ID=<id>` in the terminal. You can also retrieve it from the `_id` field of the sample room in `GET http://127.0.0.1:5000/api/rooms`. To display the ID with `curl` and Python:

```bash
curl -s http://127.0.0.1:5000/api/rooms | python -c 'import json,sys; print([(r["name"], r["_id"]) for r in json.load(sys.stdin)["rooms"]])'
```

**Find the login token:** Start the API (`npm run server`) and log in as either user. The JSON response contains a `token` field (along with `isAdmin`). To print the admin token directly:

```bash
curl -s -X POST http://127.0.0.1:5000/api/users/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"AdminPass123!"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["token"])'
```

For the regular user's token, use `test@example.com` and `TestPass123!` instead. In Swagger UI (`http://127.0.0.1:5000/docs`), `POST /api/users/login` likewise returns the token in the response body's `token` field. Use it as `Authorization: Bearer <token>` for authenticated requests. Only the admin token can create a room using `POST /api/rooms`.

**Reruns:** The script does not duplicate the same demo users or the admin's named sample room. Existing account passwords are *not* changed, so use the account's original password if it already existed. To customize passwords on first creation, set `DEMO_TEST_PASSWORD` and `DEMO_ADMIN_PASSWORD` when running the script. This script is intentionally for local/demo use only; it refuses non-SQLite databases unless `ALLOW_DEMO_SEED_NON_SQLITE=yes` is explicitly set for a disposable development database. Never use the sample passwords or demo seeding against production data.

## Main routes

- `/api/users/register`, `/api/users/login`, `/api/users/update`, `/api/users/update/password`, `/api/users`, `/api/users/{id}`
- `/api/rooms`, `/api/rooms/{id}`, `/api/rooms/{id}/reviews`
- `/api/bookings`, `/api/bookings/me`, `/api/bookings/check`, `/api/bookings/dates/{roomId}`, `/api/bookings/{id}`
- `/api/uploads`, `/uploads/{filename}`, `/api/config/paypal`, `/api/health`

**Payment limitation:** This port retains the original client-reported payment metadata flow, and does not independently verify PayPal transactions. Do not accept real-money bookings in production until server-side PayPal order verification and authoritative price calculations are implemented. Concurrent booking writes also require transaction-level locking/constraints for production. This version rejects known overlapping bookings but does not guarantee race-free inventory under simultaneous requests.
