from datetime import datetime, timezone
from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint, JSON, Text, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now():
    return datetime.now(timezone.utc).isoformat()

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (CheckConstraint("role IN ('admin','manager')"),)

class LoginSession(Base):
    __tablename__ = 'sessions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    csrf: Mapped[str] = mapped_column(String(64))
    expires: Mapped[int] = mapped_column()

class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(default=0)
    until: Mapped[int] = mapped_column()

class Event(Base):
    __tablename__ = 'events'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    date: Mapped[str] = mapped_column(String(10))
    time: Mapped[str] = mapped_column(String(5))
    address: Mapped[str] = mapped_column(String(300))
    venue: Mapped[str] = mapped_column(String(200))
    speaker: Mapped[str] = mapped_column(String(150))
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='draft')
    next_number: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(default=now)
    __table_args__ = (CheckConstraint("status IN ('draft','open','closed','completed')"), CheckConstraint('next_number > 0'))

class Registration(Base):
    __tablename__ = 'registrations'
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id'), index=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[str] = mapped_column(default=now)
    bitrix_lead_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bitrix_contact_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_registration_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

class IssueBatch(Base):
    __tablename__ = 'issue_batches'
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    registration_id: Mapped[int] = mapped_column(ForeignKey('registrations.id'))

class Ticket(Base):
    __tablename__ = 'tickets'
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('events.id'), index=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey('registrations.id'), index=True)
    batch_key: Mapped[str] = mapped_column(ForeignKey('issue_batches.key'), index=True)
    number: Mapped[int] = mapped_column()
    name: Mapped[str] = mapped_column(String(200), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[str] = mapped_column(default=now)
    cancelled: Mapped[bool] = mapped_column(default=False)
    snapshot: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('event_id', 'number'), CheckConstraint('number > 0'))

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[int] = mapped_column(index=True)
    detail: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[str] = mapped_column(default=now)
