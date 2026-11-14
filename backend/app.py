import csv
import hashlib
import hmac
import io
import json
import os
import secrets
import time
import zipfile
from datetime import date, time as clocktime
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update, func, or_
from sqlalchemy.exc import IntegrityError
from .db import get_db
from .models import User, LoginSession, LoginAttempt, Event, Registration, IssueBatch, Ticket, AuditLog
from .pdf import pdf_bytes

app = FastAPI(title='Destination Tickets', docs_url=None, redoc_url=None)
SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def hash_password(value):
    salt = secrets.token_hex(16)
    return salt + ':' + hashlib.scrypt(value.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

def verify_password(value, stored):
    salt, hashed = stored.split(':')
    actual = hashlib.scrypt(value.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(actual, hashed)

DUMMY_HASH = hash_password('constant-time-placeholder')

def audit(db, user, action, entity_id, detail=''):
    db.add(AuditLog(user_id=user.id, action=action, entity_id=entity_id, detail=detail))

def current(request: Request, db=Depends(get_db)):
    token = request.cookies.get('destination_session', '')
    session = db.get(LoginSession, digest(token))
    if not session or session.expires <= time.time():
        raise HTTPException(401, 'Войдите в систему')
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, 'Пользователь отключён')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), session.csrf):
            raise HTTPException(403, 'Недействительный CSRF-токен')
    return user

def admin(user=Depends(current)):
    if user.role != 'admin':
        raise HTTPException(403, 'Требуются права администратора')
    return user

@app.middleware('http')
async def secure_headers(request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control'] = 'no-store'
    return response

class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)

@app.post('/api/login')
def login(data: LoginIn, request: Request, response: Response, db=Depends(get_db)):
    # Browsers must send this non-simple header. Cross-origin requests cannot obtain CORS approval.
    if request.headers.get('X-Requested-With') != 'Destination':
        raise HTTPException(403, 'Недопустимый источник запроса')
    username = data.username.strip().lower()
    keys = [digest('ip:' + (request.client.host if request.client else 'unknown')), digest('user:' + username)]
    stamp = int(time.time())
    # Atomic persisted buckets; works across workers. Do not trust forwarded IP headers.
    for key in keys:
        row = db.get(LoginAttempt, key)
        if row is None:
            try:
                with db.begin_nested():
                    db.add(LoginAttempt(key=key, count=0, until=stamp+900)); db.flush()
            except IntegrityError:
                pass
        db.execute(update(LoginAttempt).where(LoginAttempt.key == key, LoginAttempt.until <= stamp).values(count=0, until=stamp+900))
        count = db.execute(update(LoginAttempt).where(LoginAttempt.key == key).values(count=LoginAttempt.count+1).returning(LoginAttempt.count)).scalar_one()
        if count > (50 if key == keys[0] else 10):
            db.commit()
            raise HTTPException(429, 'Слишком много попыток. Повторите через 15 минут')
    db.commit()
    user = db.scalar(select(User).where(User.username == username))
    valid = verify_password(data.password, user.password_hash if user else DUMMY_HASH)
    if not valid or not user or not user.active:
        raise HTTPException(401, 'Неверный логин или пароль')
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(LoginSession(id=digest(token), user_id=user.id, csrf=csrf, expires=stamp+int(os.getenv('SESSION_HOURS', '8'))*3600))
    audit(db, user, 'login', user.id); db.commit()
    response.set_cookie('destination_session', token, httponly=True, secure=SECURE, samesite='strict', max_age=int(os.getenv('SESSION_HOURS', '8'))*3600)
    return {'id': user.id, 'name': user.name, 'role': user.role, 'csrf': csrf}

@app.get('/api/me')
def me(request: Request, user=Depends(current), db=Depends(get_db)):
    return {'id': user.id, 'name': user.name, 'role': user.role, 'csrf': db.get(LoginSession, digest(request.cookies['destination_session'])).csrf}

@app.post('/api/logout')
def logout(request: Request, response: Response, user=Depends(current), db=Depends(get_db)):
    db.delete(db.get(LoginSession, digest(request.cookies['destination_session']))); db.commit()
    response.delete_cookie('destination_session')
    return {'ok': True}

class UserIn(BaseModel):
    username: str = Field(pattern=r'^[a-zA-Z0-9_.-]{3,100}$')
    name: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=12, max_length=200)
    role: Literal['admin', 'manager'] = 'manager'

@app.get('/api/users')
def users(user=Depends(admin), db=Depends(get_db)):
    return [{'id': u.id, 'username': u.username, 'name': u.name, 'role': u.role, 'active': u.active} for u in db.scalars(select(User).order_by(User.id))]

@app.post('/api/users')
def create_user(data: UserIn, user=Depends(admin), db=Depends(get_db)):
    u = User(username=data.username.lower(), name=data.name, password_hash=hash_password(data.password), role=data.role)
    db.add(u)
    try:
        db.flush(); audit(db, user, 'user.create', u.id); db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(409, 'Логин уже занят')
    return {'id': u.id}

class ActiveIn(BaseModel):
    active: bool

@app.patch('/api/users/{uid}')
def active_user(uid: int, data: ActiveIn, user=Depends(admin), db=Depends(get_db)):
    u = db.get(User, uid)
    if not u: raise HTTPException(404, 'Пользователь не найден')
    if uid == user.id: raise HTTPException(409, 'Нельзя отключить собственную учётную запись')
    u.active = data.active
    audit(db, user, 'user.active', uid, str(data.active)); db.commit()
    return {'ok': True}

class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    date: date
    time: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    address: str = Field(min_length=1, max_length=300)
    venue: str = Field(min_length=1, max_length=200)
    speaker: str = Field(min_length=1, max_length=150)
    capacity: int | None = Field(default=None, ge=1, le=1000000)
    status: Literal['draft', 'open', 'closed', 'completed'] = 'draft'

    @field_validator('title', 'city', 'address', 'venue', 'speaker')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('Поле не может быть пустым')
        return value.strip()

def event_dict(e):
    return {k: getattr(e, k) for k in ('id','title','city','date','time','address','venue','speaker','capacity','status','created_at')}

@app.get('/api/events')
def events(user=Depends(current), db=Depends(get_db)):
    totals = dict(db.execute(select(Ticket.event_id, func.count()).group_by(Ticket.event_id)).all())
    return [{**event_dict(e), 'ticket_count': totals.get(e.id, 0)} for e in db.scalars(select(Event).order_by(Event.date, Event.time))]

@app.post('/api/events')
def create_event(data: EventIn, user=Depends(admin), db=Depends(get_db)):
    e = Event(**data.model_dump(mode='json')); db.add(e); db.flush()
    audit(db, user, 'event.create', e.id); db.commit()
    return event_dict(e)

@app.put('/api/events/{eid}')
def edit_event(eid: int, data: EventIn, user=Depends(admin), db=Depends(get_db)):
    # Conditional UPDATE serializes modifications with issuance on both databases.
    query = update(Event).where(Event.id == eid)
    if data.capacity: query = query.where(Event.next_number-1 <= data.capacity)
    changed = db.execute(query.values(**data.model_dump(mode='json')).returning(Event.id)).scalar_one_or_none()
    if changed is None:
        raise HTTPException(409, 'Мероприятие не найдено или вместимость меньше количества выданных билетов')
    e = db.get(Event, eid)
    audit(db, user, 'event.update', e.id); db.commit()
    return event_dict(e)

class IssueIn(BaseModel):
    event_id: int = Field(gt=0)
    names: list[str] = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    @field_validator('names')
    @classmethod
    def validate_names(cls, names):
        cleaned = [' '.join(n.split()) for n in names]
        if any(len(n) < 2 or len(n) > 200 or any(ord(c)<32 for c in n) for n in cleaned):
            raise ValueError('Каждое ФИО должно содержать от 2 до 200 символов')
        return cleaned
    @field_validator('phone')
    @classmethod
    def validate_phone(cls, value):
        if value and (any(c not in '+0123456789 ()-' for c in value) or not 7 <= sum(c.isdigit() for c in value) <= 15):
            raise ValueError('Проверьте телефон')
        return value or None

def ticket_dict(t, db):
    r, u = db.get(Registration, t.registration_id), db.get(User, t.created_by)
    return {'id': t.id, 'event_id': t.event_id, 'registration_id': t.registration_id, 'number': f'{t.number:04d}', 'name': t.name, 'phone': r.phone, 'manager': u.name, 'created_at': t.created_at, 'cancelled': t.cancelled, 'event': t.snapshot}

@app.post('/api/tickets')
def issue(data: IssueIn, idempotency_key: str = Header(min_length=16, max_length=100), user=Depends(current), db=Depends(get_db)):
    fingerprint = digest(json.dumps(data.model_dump(), sort_keys=True, ensure_ascii=False))
    def existing(batch):
        if batch.created_by != user.id or batch.fingerprint != fingerprint:
            raise HTTPException(409, 'Ключ запроса уже использован для других данных')
        return {'batch': batch.key, 'tickets': [ticket_dict(t, db) for t in db.scalars(select(Ticket).where(Ticket.batch_key == batch.key).order_by(Ticket.number))]}
    batch = db.get(IssueBatch, idempotency_key)
    if batch: return existing(batch)
    try:
        # A single UPDATE reserves the whole range and locks the event in SQLite and PostgreSQL.
        number = db.execute(update(Event).where(Event.id == data.event_id, Event.status == 'open', or_(Event.capacity.is_(None), Event.next_number + len(data.names)-1 <= Event.capacity)).values(next_number=Event.next_number+len(data.names)).returning(Event.next_number)).scalar_one_or_none()
        if number is None:
            raise HTTPException(409, 'Регистрация закрыта, мероприятие не найдено или превышена вместимость')
        e = db.get(Event, data.event_id)
        r = Registration(event_id=e.id, phone=data.phone, created_by=user.id); db.add(r); db.flush()
        batch = IssueBatch(key=idempotency_key, fingerprint=fingerprint, created_by=user.id, registration_id=r.id)
        db.add(batch); db.flush()
        tickets = [Ticket(event_id=e.id, registration_id=r.id, batch_key=batch.key, number=number-len(data.names)+i, name=name, created_by=user.id, snapshot=event_dict(e)) for i, name in enumerate(data.names)]
        db.add_all(tickets); db.flush()
        # Validate all PDFs before committing any number or ticket.
        pdf_bytes(tickets)
        for t in tickets: audit(db, user, 'ticket.issue', t.id)
        db.commit()
        return {'batch': batch.key, 'tickets': [ticket_dict(t, db) for t in tickets]}
    except IntegrityError:
        db.rollback()
        batch = db.get(IssueBatch, idempotency_key)
        if batch: return existing(batch)
        raise HTTPException(409, 'Конфликт записи. Повторите запрос с прежним ключом')

def ticket_query(event_id=None, q='', status='all'):
    query = select(Ticket)
    if event_id: query = query.where(Ticket.event_id == event_id)
    if q:
        # Python casefold below gives consistent Unicode search across SQLite and PostgreSQL.
        pass
    if status == 'active': query = query.where(Ticket.cancelled.is_(False))
    if status == 'cancelled': query = query.where(Ticket.cancelled.is_(True))
    return query.order_by(Ticket.id.desc())

def matching(db, event_id, q, status):
    return [t for t in db.scalars(ticket_query(event_id, q, status)) if not q or q.casefold() in t.name.casefold() or q in f'{t.number:04d}']

@app.get('/api/tickets')
def tickets(event_id: int | None = None, q: str = '', status: Literal['all','active','cancelled']='all', page: int=1, user=Depends(current), db=Depends(get_db)):
    rows = matching(db, event_id, q, status); page = max(1, page)
    return {'total': len(rows), 'items': [ticket_dict(t, db) for t in rows[(page-1)*50:page*50]]}

@app.get('/api/tickets/export')
def export(event_id: int | None = None, q: str='', status: Literal['all','active','cancelled']='all', user=Depends(current), db=Depends(get_db)):
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(['Номер','ФИО','Мероприятие','Город','Телефон','Менеджер','Создан','Статус'])
    def safe(value):
        value = str(value or '')
        return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
    for t in matching(db, event_id, q, status):
        row = ticket_dict(t, db)
        writer.writerow([safe(v) for v in [row['number'], t.name, t.snapshot['title'], t.snapshot['city'], row['phone'], row['manager'], t.created_at, 'Отменён' if t.cancelled else 'Действителен']])
    audit(db, user, 'ticket.export', event_id or 0); db.commit()
    return Response(output.getvalue().encode('utf-8-sig'), media_type='text/csv', headers={'Content-Disposition':'attachment; filename=tickets.csv'})

def get_ticket(tid, db):
    t = db.get(Ticket, tid)
    if not t: raise HTTPException(404, 'Билет не найден')
    return t

@app.get('/api/tickets/{tid}/pdf')
def download(tid: int, user=Depends(current), db=Depends(get_db)):
    t = get_ticket(tid, db)
    result = pdf_bytes([t]); audit(db, user, 'ticket.download', t.id); db.commit()
    return Response(result, media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename=ticket-{t.event_id}-{t.number:04d}.pdf'})

@app.get('/api/batches/{key}/{kind}')
def batch_download(key: str, kind: Literal['pdf','zip'], user=Depends(current), db=Depends(get_db)):
    rows = list(db.scalars(select(Ticket).where(Ticket.batch_key == key).order_by(Ticket.number)))
    if not rows: raise HTTPException(404, 'Билеты не найдены')
    if kind == 'pdf': result, mime = pdf_bytes(rows), 'application/pdf'
    else:
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for t in rows: archive.writestr(f'ticket-{t.event_id}-{t.number:04d}.pdf', pdf_bytes([t]))
        result, mime = output.getvalue(), 'application/zip'
    audit(db, user, 'batch.download', rows[0].registration_id); db.commit()
    return Response(result, media_type=mime, headers={'Content-Disposition':f'attachment; filename=tickets.{kind}'})

@app.post('/api/tickets/{tid}/cancel')
def cancel(tid: int, user=Depends(admin), db=Depends(get_db)):
    t = get_ticket(tid, db)
    if not t.cancelled:
        t.cancelled = True; audit(db, user, 'ticket.cancel', tid); db.commit()
    return {'ok': True}

@app.get('/api/tickets/{tid}/history')
def history(tid: int, user=Depends(current), db=Depends(get_db)):
    get_ticket(tid, db)
    return [{'action': a.action, 'created_at': a.created_at, 'manager': db.get(User, a.user_id).name} for a in db.scalars(select(AuditLog).where(AuditLog.entity_id == tid, AuditLog.action.like('ticket.%')).order_by(AuditLog.id))]

@app.get('/api/health')
def health(): return {'status': 'ok'}

dist = Path(__file__).resolve().parents[1] / 'frontend/dist'
if dist.exists():
    app.mount('/assets', StaticFiles(directory=dist/'assets'), name='assets')
    @app.get('/')
    def index(): return FileResponse(dist/'index.html')
