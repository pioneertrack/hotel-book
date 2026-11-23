"""Isolated regression tests for room search. Run with pytest backend/test_room_search.py -q.

Uses a fresh SQLite database for each test; no .env, seeded data, or network needed.
These tests describe target behavior and are expected to fail on the original search API.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("JWT_SECRET", "local-test-secret-room-search-only-12345")

from database import Base, Booking, Room, User  # noqa: E402
from main import app, db_session  # noqa: E402


def utc(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc)


@pytest.fixture
def catalog(tmp_path):
    # Override only the search endpoint's DB session, never the global app engine.
    # A distinct on-disk SQLite database is created for every test invocation.
    db_file = tmp_path / "room_search.sqlite3"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with Session() as db:
        owner = User(name="Owner", email="owner@example.test", password="not-used", is_admin=True)
        guest = User(name="Guest", email="guest@example.test", password="not-used")
        db.add_all([owner, guest])
        db.flush()
        details = [
            # name, price, capacity, beds, category
            ("Garden King", 120, 3, 2, "King"),
            ("Garden Twins", 90, 4, 2, "Twins"),
            ("Garden Budget", 70, 2, 1, "King"),
            ("City King", 160, 5, 2, "King"),
        ]
        rooms = {}
        for name, price, capacity, beds, kind in details:
            room = Room(name=name, description="Clean room", price_per_night=price,
                        address="Test address", guest_capacity=capacity,
                        num_of_beds=beds, category=kind, owner_id=owner.id)
            db.add(room)
            db.flush()
            rooms[name] = room.id
        db.add(Booking(room_id=rooms["Garden King"], user_id=guest.id,
                       check_in_date=utc("2027-06-10"), check_out_date=utc("2027-06-12"),
                       amount_paid=240, days_of_stay=2))
        db.commit()

    def isolated_session():
        with Session() as db:
            yield db

    app.dependency_overrides[db_session] = isolated_session
    try:
        # No lifespan context: the fixture already created its schema and the
        # unrelated application engine must not create/open another database.
        client = TestClient(app)
        try:
            yield client, rooms
        finally:
            client.close()
    finally:
        app.dependency_overrides.pop(db_session, None)
        engine.dispose()


def search(catalog, **params):
    client, _ = catalog
    response = client.get("/api/rooms", params=params)
    assert response.status_code == 201, response.text  # existing endpoint contract
    payload = response.json()
    assert "rooms" in payload and "count" in payload
    return payload


def names(result):
    return {room["name"] for room in result["rooms"]}


def test_unfiltered_search_remains_public_and_returns_all_rooms(catalog):
    result = search(catalog)
    assert result["count"] == 4
    assert names(result) == {"Garden King", "Garden Twins", "Garden Budget", "City King"}


def test_existing_filters_still_work_together(catalog):
    result = search(catalog, keyword="Garden", numOfBeds=2, roomType="King")
    assert result["count"] == 1
    assert names(result) == {"Garden King"}


def test_dates_exclude_overlapping_reservations(catalog):
    result = search(catalog, checkInDate="2027-06-11", checkOutDate="2027-06-13")
    assert result["count"] == 3
    assert "Garden King" not in names(result)
    assert names(result) == {"Garden Twins", "Garden Budget", "City King"}


def test_non_overlapping_dates_keep_room_available(catalog):
    result = search(catalog, checkInDate="2027-06-13", checkOutDate="2027-06-15")
    assert result["count"] == 4
    assert "Garden King" in names(result)


def test_guest_count_is_minimum_required_capacity(catalog):
    result = search(catalog, guestCount=4)
    assert result["count"] == 2
    assert names(result) == {"Garden Twins", "City King"}


def test_price_range_is_inclusive_and_each_bound_works_alone(catalog):
    both = search(catalog, minPrice=90, maxPrice=120)
    assert both["count"] == 2
    assert names(both) == {"Garden King", "Garden Twins"}
    lower = search(catalog, minPrice=160)
    assert lower["count"] == 1
    assert names(lower) == {"City King"}
    upper = search(catalog, maxPrice=70)
    assert upper["count"] == 1
    assert names(upper) == {"Garden Budget"}


def test_new_and_existing_filters_combine(catalog):
    result = search(catalog, checkInDate="2027-06-11", checkOutDate="2027-06-13",
                    guestCount=3, minPrice=80, maxPrice=100,
                    keyword="Garden", numOfBeds=2, roomType="Twins")
    assert result["count"] == 1
    assert names(result) == {"Garden Twins"}
    none = search(catalog, checkInDate="2027-06-11", checkOutDate="2027-06-13",
                  guestCount=3, minPrice=100, maxPrice=140,
                  keyword="Garden", numOfBeds=2, roomType="King")
    assert none["count"] == 0
    assert none["rooms"] == []


@pytest.mark.parametrize("params", [
    {"checkInDate": "2027-06-11"},
    {"checkOutDate": "2027-06-13"},
    {"checkInDate": "2027-06-13", "checkOutDate": "2027-06-11"},
    {"checkInDate": "2027-06-11", "checkOutDate": "2027-06-11"},
    {"checkInDate": "invalid", "checkOutDate": "2027-06-13"},
    {"guestCount": 0},
    {"guestCount": "abc"},
    {"minPrice": -1},
    {"maxPrice": -1},
    {"minPrice": 200, "maxPrice": 100},
])
def test_invalid_search_parameters_return_422(catalog, params):
    client, _ = catalog
    response = client.get("/api/rooms", params=params)
    assert response.status_code == 422, response.text
