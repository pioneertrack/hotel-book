"""FastAPI backend preserving the original React application's /api contract."""
import os
import math
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any
import hashlib
import hmac
import jwt
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session, selectinload
from pydantic import BaseModel, Field
from database import Base, engine, SessionLocal, User, Room, RoomImage, Review, Booking, now

SECRET = os.getenv("JWT_SECRET", "")
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if len(SECRET) < 20 or SECRET == "replace-with-a-long-random-development-secret":
        raise RuntimeError("Set a unique JWT_SECRET (20+ characters) in .env")
    Base.metadata.create_all(engine)
    yield

app = FastAPI(title="Hotel Booking API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

def db_session():
    with SessionLocal() as session:
        yield session

def error(code: int, message: str):
    raise HTTPException(status_code=code, detail=message)

@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"success": False, "message": exc.detail})

def iso(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")

def parse_date(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        error(422, "Invalid date format")

def user_json(u, auth=False):
    output = {"_id": u.id, "name": u.name, "email": u.email, "avatar": u.avatar, "isAdmin": u.is_admin, "createdAt": iso(u.created_at), "updatedAt": iso(u.updated_at)}
    if auth:
        output["id"] = u.id
        output["token"] = jwt.encode({"id": u.id}, SECRET, algorithm="HS256")
    return output

def room_json(r):
    return {"_id": r.id, "name": r.name, "description": r.description,
        "images": [{"_id": i.id, "image": i.image} for i in r.images], "pricePerNight": r.price_per_night,
        "address": r.address, "guestCapacity": r.guest_capacity, "numOfBeds": r.num_of_beds,
        "internet": r.internet, "breakfast": r.breakfast, "airConditioned": r.air_conditioned,
        "petsAllowed": r.pets_allowed, "roomCleaning": r.room_cleaning,
        "ratings": sum(x.rating for x in r.reviews)/len(r.reviews) if r.reviews else 0,
        "numOfReviews": len(r.reviews), "category": r.category, "user": r.owner_id,
        "reviews": [{"_id": x.id, "user": x.user_id, "name": x.name, "rating": x.rating, "comment": x.comment} for x in r.reviews],
        "createdAt": iso(r.created_at), "updatedAt": iso(r.updated_at)}

def booking_json(b, user_info=False, room_info=False, room_images=False):
    data = {"_id": b.id, "room": {"_id": b.room.id, "name": b.room.name, **({"images": [{"_id": i.id, "image": i.image} for i in b.room.images]} if room_images else {})} if room_info else b.room_id,
        "user": {"_id": b.user.id, "name": b.user.name, "email": b.user.email} if user_info else b.user_id,
        "checkInDate": iso(b.check_in_date), "checkOutDate": iso(b.check_out_date), "amountPaid": b.amount_paid,
        "daysOfStay": b.days_of_stay, "paymentInfo": {"id": b.payment_id, "status": b.payment_status, "update_time": iso(b.payment_update_time), "email_address": b.payment_email},
        "paidAt": iso(b.paid_at), "createdAt": iso(b.created_at), "updatedAt": iso(b.updated_at)}
    return data

def current_user(request: Request, db: Session = Depends(db_session)):
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        error(401, "no token, no auth")
    try:
        user_id = jwt.decode(header.split(" ", 1)[1], SECRET, algorithms=["HS256"])["id"]
        user = db.get(User, user_id)
        if user is None:
            error(401, "no token, no auth")
        return user
    except (jwt.PyJWTError, KeyError):
        error(401, "no token, no auth")

def admin_user(user: User = Depends(current_user)):
    if not user.is_admin:
        error(403, "Admin access required")
    return user

def get_room(db, id):
    room = db.get(Room, id)
    if not room:
        error(404, "Room not found")
    return room

def get_user(db, id):
    user = db.get(User, id)
    if not user:
        error(404, "User not found")
    return user

def unique_email(db, email, exclude=None):
    if db.scalar(select(User).where(User.email == email.lower().strip(), User.id != exclude)):
        error(409, "Email already registered")

def hashed(password):
    if not password or len(password.encode()) > 72:
        error(422, "Password must be 1 to 72 bytes")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    return f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"

def verify_password(password, stored):
    try:
        scheme, iterations, salt, digest = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(actual, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False

class RegisterBody(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)
    avatar: str | None = None
class LoginBody(BaseModel):
    email: str
    password: str
class RoomBody(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    images: list[dict[str, Any]] = []
    pricePerNight: float = Field(ge=0)
    address: str = Field(min_length=1)
    guestCapacity: int = Field(ge=1)
    numOfBeds: int = Field(ge=1)
    internet: bool = False
    breakfast: bool = False
    airConditioned: bool = False
    petsAllowed: bool = False
    roomCleaning: bool = False
    category: str
class ReviewBody(BaseModel):
    rating: float = Field(ge=1, le=5)
    comment: str = Field(min_length=1)
class CheckBody(BaseModel):
    roomId: str
    checkInDate: str
    checkOutDate: str
class BookingBody(BaseModel):
    room: str
    checkInDate: str
    checkOutDate: str
    amountPaid: float = Field(ge=0)
    daysOfStay: int = Field(ge=1)
    paymentInfo: dict[str, Any] = {}

def room_fields(r, body):
    if body.category not in ("King", "Single", "Twins"):
        error(422, "Invalid room category")
    for key, val in {"name": body.name, "description": body.description, "price_per_night": body.pricePerNight, "address": body.address,
        "guest_capacity": body.guestCapacity, "num_of_beds": body.numOfBeds, "category": body.category,
        "internet": body.internet, "breakfast": body.breakfast, "air_conditioned": body.airConditioned,
        "pets_allowed": body.petsAllowed, "room_cleaning": body.roomCleaning}.items():
        setattr(r, key, val)
    r.images = [RoomImage(image=str(i.get("image", ""))) for i in body.images if i.get("image")]

def overlaps(db, room_id, check_in, check_out):
    # Checkout is treated as inclusive to match the existing calendar behavior.
    return db.scalar(select(Booking.id).where(Booking.room_id == room_id, Booking.check_in_date <= check_out, Booking.check_out_date >= check_in).limit(1)) is not None

@app.get("/api")
def home():
    return {"message": "Welcome to Hotel Booking App"}
@app.get("/api/health")
def health():
    return {"status": "ok"}
@app.get("/api/config/paypal")
def paypal_config():
    val = os.getenv("PAYPAL_CLIENT_ID", "")
    if not val:
        error(503, "PayPal is not configured. Set PAYPAL_CLIENT_ID for checkout.")
    return PlainTextResponse(val)

@app.post("/api/users/register", status_code=201)
def register(body: RegisterBody, db: Session = Depends(db_session)):
    email = body.email.lower().strip()
    unique_email(db, email)
    user = User(name=body.name, email=email, password=hashed(body.password), avatar=body.avatar)
    db.add(user); db.commit(); db.refresh(user)
    return user_json(user, True)
@app.post("/api/users/login", status_code=201)
def login(body: LoginBody, db: Session = Depends(db_session)):
    user = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if not user or not verify_password(body.password, user.password):
        error(401, "Email or password incorrect")
    return user_json(user, True)
@app.put("/api/users/update", status_code=201)
def update_profile(payload: dict, user: User = Depends(current_user), db: Session = Depends(db_session)):
    if "email" in payload:
        email = str(payload["email"]).lower().strip()
        unique_email(db, email, user.id)
        user.email = email
    for field in ("name", "avatar"):
        if field in payload:
            setattr(user, field, payload[field])
    db.commit(); db.refresh(user)
    return user_json(user, True)
@app.put("/api/users/update/password", status_code=201)
def change_password(payload: dict, user: User = Depends(current_user), db: Session = Depends(db_session)):
    if not verify_password(str(payload.get("oldPassword", "")), user.password):
        error(401, "Old password incorrect")
    user.password = hashed(str(payload.get("newPassword", "")))
    db.commit(); db.refresh(user)
    return user_json(user, True)
@app.get("/api/users", status_code=201)
def list_users(pageNumber: int = 1, db: Session = Depends(db_session), admin: User = Depends(admin_user)):
    page = max(1, pageNumber)
    count = db.scalar(select(func.count()).select_from(User))
    users = db.scalars(select(User).order_by(User.created_at).offset((page-1)*4).limit(4)).all()
    return {"users": [user_json(u) for u in users], "page": page, "pages": math.ceil(count/4), "count": count}
@app.get("/api/users/{id}", status_code=201)
def single_user(id: str, db: Session = Depends(db_session), admin: User = Depends(admin_user)):
    return user_json(get_user(db, id))
@app.put("/api/users/{id}", status_code=201)
def admin_update_user(id: str, payload: dict, db: Session = Depends(db_session), admin: User = Depends(admin_user)):
    u = get_user(db, id)
    if "email" in payload:
        email = str(payload["email"]).lower().strip()
        unique_email(db, email, u.id)
        u.email = email
    for field in ("name", "avatar"):
        if field in payload:
            setattr(u, field, payload[field])
    if "isAdmin" in payload:
        u.is_admin = bool(payload["isAdmin"])
    db.commit(); db.refresh(u)
    return user_json(u)
@app.delete("/api/users/{id}", status_code=201)
def delete_user(id: str, db: Session = Depends(db_session), admin: User = Depends(admin_user)):
    u = get_user(db, id)
    if db.scalar(select(Room.id).where(Room.owner_id == id).limit(1)) or db.scalar(select(Booking.id).where(Booking.user_id == id).limit(1)) or db.scalar(select(Review.id).where(Review.user_id == id).limit(1)):
        error(409, "User has associated rooms, bookings, or reviews")
    db.delete(u); db.commit()
    return {}

@app.get("/api/rooms", status_code=201)
def list_rooms(pageNumber: int = 1, keyword: str = "", numOfBeds: int | None = None, roomType: str = "", db: Session = Depends(db_session)):
    page = max(1, pageNumber)
    query = select(Room)
    if keyword:
        query = query.where(or_(Room.name.ilike(f"%{keyword}%"), Room.description.ilike(f"%{keyword}%")))
    if numOfBeds is not None:
        query = query.where(Room.num_of_beds == numOfBeds)
    if roomType:
        query = query.where(Room.category == roomType)
    count = db.scalar(select(func.count()).select_from(query.subquery()))
    rooms = db.scalars(query.order_by(Room.created_at).offset((page-1)*4).limit(4)).all()
    return {"rooms": [room_json(r) for r in rooms], "page": page, "pages": math.ceil(count/4), "count": count}
@app.post("/api/rooms", status_code=201)
def create_room(body: RoomBody, db: Session = Depends(db_session), admin: User = Depends(admin_user)):
    r = Room(owner_id=admin.id)
    room_fields(r, body)
    db.add(r); db.commit(); db.refresh(r)
    return room_json(r)
@app.get("/api/rooms/{id}", status_code=201)
def single_room(id: str, db: Session = Depends(db_session)):
    return room_json(get_room(db, id))
@app.put("/api/rooms/{id}", status_code=201)
def update_room(id: str, body: RoomBody, db: Session = Depends(db_session), user: User = Depends(current_user)):
    r = get_room(db, id)
    if not user.is_admin and r.owner_id != user.id:
        error(403, "Room owner or admin required")
    room_fields(r, body)
    db.commit(); db.refresh(r)
    return room_json(r)
@app.delete("/api/rooms/{id}", status_code=201)
def delete_room(id: str, db: Session = Depends(db_session), admin: User = Depends(admin_user)):
    db.delete(get_room(db, id)); db.commit()
    return {}
@app.post("/api/rooms/{id}/reviews", status_code=201)
def add_review(id: str, body: ReviewBody, db: Session = Depends(db_session), user: User = Depends(current_user)):
    r = get_room(db, id)
    if any(x.user_id == user.id for x in r.reviews):
        error(409, "Already reviewed")
    db.add(Review(room_id=id, user_id=user.id, name=user.name, rating=body.rating, comment=body.comment))
    db.commit()
    return {"message": "Review added"}

@app.post("/api/bookings/check", status_code=201)
def check_booking(body: CheckBody, db: Session = Depends(db_session)):
    get_room(db, body.roomId)
    start, end = parse_date(body.checkInDate), parse_date(body.checkOutDate)
    if end <= start:
        error(422, "Check-out must be after check-in")
    return {"roomAvailable": not overlaps(db, body.roomId, start, end)}
@app.post("/api/bookings", status_code=201)
def create_booking(body: BookingBody, db: Session = Depends(db_session), user: User = Depends(current_user)):
    get_room(db, body.room)
    start, end = parse_date(body.checkInDate), parse_date(body.checkOutDate)
    if end <= start:
        error(422, "Check-out must be after check-in")
    if overlaps(db, body.room, start, end):
        error(409, "Room already booked for these dates")
    info = body.paymentInfo
    b = Booking(room_id=body.room, user_id=user.id, check_in_date=start, check_out_date=end,
        amount_paid=body.amountPaid, days_of_stay=body.daysOfStay, payment_id=info.get("id"), payment_status=info.get("status"),
        payment_update_time=parse_date(info["update_time"]) if info.get("update_time") else None,
        payment_email=info.get("email_address"))
    db.add(b); db.commit(); db.refresh(b)
    return booking_json(b)
@app.get("/api/bookings/me", status_code=201)
def my_bookings(db: Session = Depends(db_session), user: User = Depends(current_user)):
    result = db.scalars(select(Booking).where(Booking.user_id == user.id).order_by(Booking.created_at.desc())).all()
    return [booking_json(b, True, True, True) for b in result]
@app.get("/api/bookings/dates/{roomId}")
def booked_dates(roomId: str, db: Session = Depends(db_session)):
    get_room(db, roomId)
    dates = []
    for b in db.scalars(select(Booking).where(Booking.room_id == roomId)):
        day = b.check_in_date.date()
        end = b.check_out_date.date()
        while day <= end:
            dates.append(iso(datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)))
            day += timedelta(days=1)
    return dates
@app.get("/api/bookings", status_code=201)
def list_bookings(pageNumber: int = 1, db: Session = Depends(db_session), admin: User = Depends(admin_user)):
    page = max(1, pageNumber)
    count = db.scalar(select(func.count()).select_from(Booking))
    items = db.scalars(select(Booking).order_by(Booking.created_at).offset((page-1)*4).limit(4)).all()
    return {"bookings": [booking_json(b, True, True) for b in items], "page": page, "pages": math.ceil(count/4), "count": count}
@app.delete("/api/bookings/{id}", status_code=201)
def delete_booking(id: str, db: Session = Depends(db_session), admin: User = Depends(admin_user)):
    booking = db.get(Booking, id)
    if not booking:
        error(404, "Booking not found")
    db.delete(booking); db.commit()
    return {}

@app.post("/api/uploads")
async def upload_images(image: list[UploadFile] = File(...)):
    if len(image) > 10:
        error(422, "Maximum 10 images")
    files = []
    for item in image:
        suffix = Path(item.filename or "").suffix.lower()
        if suffix not in (".jpg", ".jpeg", ".png") or item.content_type not in ("image/jpeg", "image/png"):
            error(422, "Images only")
        data = await item.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            error(413, "Image exceeds 5 MB")
        if not ((suffix == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n")) or (suffix in (".jpg", ".jpeg") and data.startswith(b"\xff\xd8\xff"))):
            error(422, "Invalid image content")
        name = f"image-{secrets.token_hex(12)}{suffix}"
        (UPLOAD_DIR / name).write_bytes(data)
        files.append({"fieldname": "image", "originalname": item.filename, "mimetype": item.content_type, "filename": name, "path": f"uploads/{name}", "size": len(data)})
    return files
