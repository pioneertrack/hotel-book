"""Create local development-only accounts and a sample room; safe to rerun.

Run from project root: python backend/seed_demo.py
Do not run against a production DATABASE_URL.
"""
import os
from sqlalchemy import select
from database import Base, engine, SessionLocal, User, Room
from main import hashed

TEST_EMAIL = "test@example.com"
ADMIN_EMAIL = "admin@example.com"
TEST_PASSWORD = os.getenv("DEMO_TEST_PASSWORD", "TestPass123!")
ADMIN_PASSWORD = os.getenv("DEMO_ADMIN_PASSWORD", "AdminPass123!")
ROOM_NAME = "Demo King Room"


def ensure_user(db, name, email, password, admin=False):
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(name=name, email=email, password=hashed(password), is_admin=admin)
        db.add(user)
        db.flush()
        status = "created"
    else:
        status = "already exists (password unchanged)"
        if admin and not user.is_admin:
            user.is_admin = True
            status += "; granted admin"
    return user, status


def main():
    url = str(engine.url)
    if not url.startswith("sqlite") and os.getenv("ALLOW_DEMO_SEED_NON_SQLITE") != "yes":
        raise SystemExit("Refusing to seed a non-SQLite database. For a disposable development database only, set ALLOW_DEMO_SEED_NON_SQLITE=yes.")
    print(f"Database:  {engine.url.render_as_string(hide_password=True)}")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        test, test_status = ensure_user(db, "Test User", TEST_EMAIL, TEST_PASSWORD)
        admin, admin_status = ensure_user(db, "Demo Admin", ADMIN_EMAIL, ADMIN_PASSWORD, admin=True)
        room = db.scalar(select(Room).where(Room.owner_id == admin.id, Room.name == ROOM_NAME))
        room_status = "already exists"
        if room is None:
            room = Room(
                owner_id=admin.id,
                name=ROOM_NAME,
                description="Sample room for local booking and API tests.",
                price_per_night=120.0,
                address="123 Demo Street, Test City",
                guest_capacity=2,
                num_of_beds=1,
                category="King",
                internet=True,
                breakfast=True,
                air_conditioned=True,
                pets_allowed=False,
                room_cleaning=True,
            )
            db.add(room)
            room_status = "created"
        db.commit()
        print(f"Test user: {TEST_EMAIL} [{test_status}]")
        print(f"Admin:     {ADMIN_EMAIL} [{admin_status}]")
        print(f"Room:      {ROOM_NAME} [{room_status}]")
        print(f"ROOM_ID={room.id}")
        print("Use POST /api/users/login to obtain a fresh token (the JSON field named 'token').")
        if "already exists" in test_status or "already exists" in admin_status:
            print("Existing users retain their previous passwords; demo defaults may not log them in.")
        print("WARNING: Default passwords are for local demo data only. Do not use in production.")


if __name__ == "__main__":
    main()
