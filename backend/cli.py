import argparse
import getpass
from sqlalchemy import select
from .db import Session
from .models import User, Event
from .app import hash_password

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['create-admin', 'demo'])
    parser.add_argument('--username', default='admin')
    args = parser.parse_args()
    with Session() as db:
        if args.command == 'create-admin':
            password = getpass.getpass('Пароль (не менее 12 символов): ')
            if len(password) < 12: parser.error('Пароль слишком короткий')
            if password != getpass.getpass('Повторите пароль: '): parser.error('Пароли не совпадают')
            if db.scalar(select(User).where(User.username == args.username.lower())): parser.error('Логин занят')
            db.add(User(username=args.username.lower(), name='Администратор', password_hash=hash_password(password), role='admin'))
        else:
            if db.scalar(select(Event).where(Event.venue == 'Демо-площадка «Горизонт»')):
                print('Демо уже создано'); return
            db.add(Event(title='Высшее образование за рубежом — демо', city='Тестовый город', date='2026-12-20', time='11:00', address='Учебная улица, 10 (вымышленный адрес)', venue='Демо-площадка «Горизонт»', speaker='Демонстрационный спикер', capacity=100, status='open'))
        db.commit()
    print('Готово')

if __name__ == '__main__': main()
