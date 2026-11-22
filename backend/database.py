import os
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, String, Boolean, DateTime, Integer, Float, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from pathlib import Path

# Always load the project's .env, regardless of the directory the command runs from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def resolve_database_url(raw_url: str) -> str:
    """Resolve relative SQLite filenames against the project root, not the shell cwd.

    Absolute SQLite paths, in-memory databases and non-SQLite URLs are unchanged.
    """
    url = make_url(raw_url)
    if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
        path = Path(url.database)
        if not path.is_absolute():
            url = url.set(database=str((PROJECT_ROOT / path).resolve()))
    return url.render_as_string(hide_password=False)


DATABASE_URL = resolve_database_url(os.getenv("DATABASE_URL", "sqlite:///./hotel_booking.db"))
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def new_id():
    return uuid4().hex[:24]
def now():
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass
class Timestamped:
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
class User(Timestamped, Base):
    __tablename__ = "users"
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password: Mapped[str] = mapped_column(String(255))
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    rooms: Mapped[list["Room"]] = relationship(back_populates="owner")
class Room(Timestamped, Base):
    __tablename__ = "rooms"
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    price_per_night: Mapped[float] = mapped_column(Float)
    address: Mapped[str] = mapped_column(Text)
    guest_capacity: Mapped[int] = mapped_column(Integer)
    num_of_beds: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(24))
    internet: Mapped[bool] = mapped_column(Boolean, default=False)
    breakfast: Mapped[bool] = mapped_column(Boolean, default=False)
    air_conditioned: Mapped[bool] = mapped_column(Boolean, default=False)
    pets_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    room_cleaning: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    owner: Mapped[User] = relationship(back_populates="rooms")
    images: Mapped[list["RoomImage"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    reviews: Mapped[list["Review"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="room", cascade="all, delete-orphan")
class RoomImage(Base):
    __tablename__ = "room_images"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"))
    image: Mapped[str] = mapped_column(Text)
    room: Mapped[Room] = relationship(back_populates="images")
class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200))
    rating: Mapped[float] = mapped_column(Float)
    comment: Mapped[str] = mapped_column(Text)
    room: Mapped[Room] = relationship(back_populates="reviews")
class Booking(Timestamped, Base):
    __tablename__ = "bookings"
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    check_in_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    check_out_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amount_paid: Mapped[float] = mapped_column(Float)
    days_of_stay: Mapped[int] = mapped_column(Integer)
    payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payment_update_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    room: Mapped[Room] = relationship(back_populates="bookings")
    user: Mapped[User] = relationship()
