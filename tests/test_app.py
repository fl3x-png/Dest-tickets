from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile
from urllib.parse import unquote
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import select
from backend.app import app
from backend.db import Session
from backend.models import Event
from backend.app import ticket_filename
from types import SimpleNamespace

def test_safe_ticket_filename():
    assert ticket_filename(SimpleNamespace(number=1,name='Илья Примеров')) == '1. Илья Примеров.pdf'
    name = ticket_filename(SimpleNamespace(number=8,name='../../Имя\\Фамилия:"?*<>|\r\n'))
    assert not any(c in name for c in '/\\:"?*<>|\r\n')
    assert name.startswith('8. ') and name.endswith('.pdf')
    assert len(ticket_filename(SimpleNamespace(number=99,name='Д'*200)).encode('utf-8')) < 200

def test_current_ticket_preview_assets(admin):
    assert TestClient(app).get('/api/ticket-assets/speaker.png').status_code == 401
    assert admin.get('/api/ticket-assets/speaker.png').headers['content-type'] == 'image/png'
    assert admin.get('/api/ticket-assets/flag-9.png').status_code == 200
    assert admin.get('/api/ticket-assets/other.png').status_code == 404

def event(client, **changes):
    data = dict(title='Демонстрационная презентация',city='Тестовый город',date='2026-12-20',time='11:00',address='Вымышленная улица, 10',venue='Учебный зал',speaker='Тестовый спикер',status='open',capacity=None)
    data.update(changes)
    result = client.post('/api/events',json=data)
    assert result.status_code == 200, result.text
    return result.json()

def issue(client, eid, names=None, key=None):
    return client.post('/api/tickets', json={'event_id':eid,'names':names or ['Тестовый Участник']},headers={'Idempotency-Key':key or str(uuid4())})

def test_first_batch_separate_event_and_pdf(admin):
    e = event(admin)
    batch = issue(admin,e['id'],['Иван Примеров','Анна Примерова','Алексей Примеров']).json()
    assert [t['number'] for t in batch['tickets']] == ['1','2','3']
    second = event(admin,city='Другой город')
    assert issue(admin,second['id']).json()['tickets'][0]['number'] == '1'
    t = batch['tickets'][0]
    first = admin.get(f"/api/tickets/{t['id']}/pdf")
    assert first.status_code == 200
    assert unquote(first.headers['content-disposition'].split("filename*=UTF-8''")[1]) == '1. Иван Примеров.pdf'
    assert first.content == admin.get(f"/api/tickets/{t['id']}/pdf").content
    reader = PdfReader(BytesIO(first.content))
    text = reader.pages[0].extract_text()
    assert 'Иван Примеров' in text and 'БИЛЕТ № 1' in text and '0001' not in text and 'Тестовый город' in text
    assert '20 декабря (вс) начало 11:00' in text
    assert 'АНГЛИЯ' in text and 'МАЛАЙЗИЯ' in text
    assert len(reader.pages[0].images) == 11  # Ten flags and original speaker photo.
    assert float(reader.pages[0].mediabox.width) == 1264
    assert float(reader.pages[0].mediabox.height) == 669
    font_objects = reader.pages[0]['/Resources']['/Font']
    assert any('/FontFile2' in f.get_object().get('/FontDescriptor',{}) for f in font_objects.values() if '/FontDescriptor' in f.get_object())
    combined = admin.get(f"/api/batches/{batch['batch']}/pdf")
    assert len(PdfReader(BytesIO(combined.content)).pages) == 3
    zipped = admin.get(f"/api/batches/{batch['batch']}/zip")
    with ZipFile(BytesIO(zipped.content)) as z:
        assert len(z.namelist()) == 3
        assert z.namelist() == ['1. Иван Примеров.pdf', '2. Анна Примерова.pdf', '3. Алексей Примеров.pdf']
        assert all(z.read(n).startswith(b'%PDF') for n in z.namelist())

def test_idempotency_payload_conflict_and_cancel_number(admin):
    e = event(admin); key=str(uuid4())
    a = issue(admin,e['id'],key=key)
    b = issue(admin,e['id'],key=key)
    assert a.json() == b.json()
    assert issue(admin,e['id'],['Другой Участник'],key).status_code == 409
    tid=a.json()['tickets'][0]['id']
    assert admin.post(f'/api/tickets/{tid}/cancel').status_code == 200
    assert issue(admin,e['id']).json()['tickets'][0]['number'] == '2'
    history=admin.get(f'/api/tickets/{tid}/history').json()
    assert [h['action'] for h in history] == ['ticket.issue','ticket.cancel']

def test_concurrent_managers_and_same_request(admin, manager):
    eid = event(admin)['id']
    def create(i):
        return issue(admin if i%2 else manager,eid,[f'Тестовый Гость {i}']).json()['tickets'][0]['number']
    with ThreadPoolExecutor(max_workers=6) as pool:
        numbers = list(pool.map(create,range(12)))
    assert sorted(map(int,numbers)) == list(range(1,13))
    key = str(uuid4())
    def retry(_): return issue(admin,eid,key=key)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(retry,range(4)))
    assert all(r.status_code == 200 for r in results)
    assert len({r.json()['tickets'][0]['id'] for r in results}) == 1
    with Session() as db:
        assert db.get(Event,eid).next_number == 14

def test_roles_auth_csrf_and_user_management(admin, manager):
    eid=event(admin)['id']; tid=issue(manager,eid).json()['tickets'][0]['id']
    anonymous=TestClient(app)
    assert anonymous.get(f'/api/tickets/{tid}/pdf').status_code == 401
    assert anonymous.get('/api/tickets').status_code == 401
    assert manager.post('/api/events',json={}).status_code == 403
    assert manager.post(f'/api/tickets/{tid}/cancel').status_code == 403
    assert manager.get('/api/users').status_code == 403
    csrf=manager.headers.pop('X-CSRF-Token')
    assert issue(manager,eid).status_code == 403
    manager.headers['X-CSRF-Token']=csrf
    uid=admin.post('/api/users',json={'username':'newmanager','name':'Вымышленный менеджер','password':'Long-demo-password!','role':'manager'}).json()['id']
    assert admin.patch(f'/api/users/{uid}',json={'active':False}).status_code == 200
    assert admin.post('/api/logout').status_code == 200
    assert admin.get('/api/me').status_code == 401

def test_capacity_closed_validation_and_snapshot(admin):
    e=event(admin,capacity=2)
    assert issue(admin,e['id'],['Тест Один','Тест Два','Тест Три']).status_code == 409
    assert issue(admin,e['id'],[' ']).status_code == 422
    batch=issue(admin,e['id']).json()
    data={k:v for k,v in e.items() if k not in ['id','created_at']};data['city']='Новый город'
    assert admin.put(f"/api/events/{e['id']}",json=data).status_code == 200
    tid=batch['tickets'][0]['id'];text=PdfReader(BytesIO(admin.get(f'/api/tickets/{tid}/pdf').content)).pages[0].extract_text()
    assert 'Тестовый город' in text and 'Новый город' not in text
    assert issue(admin,e['id']).status_code == 200
    assert issue(admin,e['id']).status_code == 409
    closed=event(admin,status='closed')
    assert issue(admin,closed['id']).status_code == 409

def test_unicode_search_csv_and_long_name(admin):
    eid=event(admin)['id']
    name='Длинное Имя ' * 15
    b=issue(admin,eid,[name.strip(),'=FORMULA Тест']).json()
    assert admin.get('/api/tickets?q=длинное').json()['total']==1
    assert admin.get('/api/tickets?q=0002').json()['total']==1
    assert admin.get('/api/tickets?q=2').json()['total']==1
    export=admin.get('/api/tickets/export').content.decode('utf-8-sig')
    assert "'=FORMULA" in export
    pdf=admin.get(f"/api/tickets/{b['tickets'][0]['id']}/pdf").content
    assert len(PdfReader(BytesIO(pdf)).pages)==1

def test_login_limit_and_browser_origin():
    c=TestClient(app)
    assert c.post('/api/login',json={'username':'admin','password':'bad'}).status_code==403
    for _ in range(10):
        assert c.post('/api/login',json={'username':'admin','password':'bad'},headers={'X-Requested-With':'Destination'}).status_code==401
    assert c.post('/api/login',json={'username':'admin','password':'bad'},headers={'X-Requested-With':'Destination'}).status_code==429

def test_event_deletion_preserves_tickets_and_blocks_issuance(admin, manager):
    e = event(admin)
    batch = issue(admin, e['id']).json()
    tid = batch['tickets'][0]['id']
    assert manager.delete(f"/api/events/{e['id']}").status_code == 403
    assert admin.delete(f"/api/events/{e['id']}").status_code == 200
    assert admin.delete(f"/api/events/{e['id']}").status_code == 200
    assert admin.get('/api/events').json() == []
    assert issue(admin, e['id']).status_code == 409
    assert admin.get(f'/api/tickets/{tid}/pdf').status_code == 200
    assert admin.get('/api/tickets').json()['total'] == 1
    assert admin.delete('/api/events/999999').status_code == 404
    data = {k:v for k,v in e.items() if k not in ('id','created_at')}
    assert admin.put(f"/api/events/{e['id']}", json=data).status_code == 409
    with Session() as db:
        assert db.get(Event, e['id']).next_number == 2
