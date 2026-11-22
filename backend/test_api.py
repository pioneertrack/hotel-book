"""Run with: pip install httpx pytest; JWT_SECRET=... pytest backend/test_api.py"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('JWT_SECRET', 'local-test-secret-only-123456789')
import tempfile

test_dir = Path(tempfile.mkdtemp(prefix="hotel-book-test-"))
test_db = test_dir / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{test_db.as_posix()}"
from fastapi.testclient import TestClient
from main import app
from database import SessionLocal, User


def test_hotel_booking_flow():
    with TestClient(app) as client:
        assert client.get('/api/health').json() == {'status': 'ok'}
        reg = client.post('/api/users/register', json={'name': 'Test', 'email': 'test@example.com', 'password': 'test-password'})
        assert reg.status_code == 201
        assert client.post('/api/users/login', json={'email': 'test@example.com', 'password': 'test-password'}).status_code == 201
        user_id, token = reg.json()['id'], reg.json()['token']
        headers = {'Authorization': 'Bearer ' + token}
        assert client.get('/api/users').status_code == 401
        with SessionLocal() as db:
            user = db.get(User, user_id)
            user.is_admin = True
            db.commit()
        room = client.post('/api/rooms', headers=headers, json={'name':'Room', 'description':'Clean room', 'address':'Main St', 'category':'King', 'guestCapacity':2, 'numOfBeds':1, 'pricePerNight':100, 'images':[]})
        assert room.status_code == 201, room.text
        room_id = room.json()['_id']
        assert client.get('/api/rooms').json()['count'] == 1
        dates = {'roomId':room_id, 'checkInDate':'2027-05-01T00:00:00Z','checkOutDate':'2027-05-03T00:00:00Z'}
        assert client.post('/api/bookings/check', json=dates).json()['roomAvailable']
        booking = client.post('/api/bookings', headers=headers, json={'room':room_id, 'checkInDate':dates['checkInDate'], 'checkOutDate':dates['checkOutDate'], 'amountPaid':200, 'daysOfStay':2, 'paymentInfo':{}})
        assert booking.status_code == 201, booking.text
        assert not client.post('/api/bookings/check', json=dates).json()['roomAvailable']
        assert client.post('/api/bookings', headers=headers, json={'room':room_id, 'checkInDate':dates['checkInDate'], 'checkOutDate':dates['checkOutDate'], 'amountPaid':200, 'daysOfStay':2}).status_code == 409
        assert len(client.get('/api/bookings/me',headers=headers).json()) == 1
        assert len(client.get('/api/bookings/dates/'+room_id).json()) == 3
        assert client.post('/api/rooms/'+room_id+'/reviews',headers=headers,json={'rating':5,'comment':'Nice'}).status_code == 201
        assert client.post('/api/rooms/'+room_id+'/reviews',headers=headers,json={'rating':5,'comment':'Again'}).status_code == 409
        assert client.get('/api/rooms/'+room_id).json()['ratings'] == 5
