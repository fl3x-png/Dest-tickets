import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()
Path('data').mkdir(exist_ok=True)
URL = os.getenv('DATABASE_URL', 'sqlite:///./data/destination.db')
engine = create_engine(URL, connect_args={'check_same_thread': False, 'timeout': 30} if URL.startswith('sqlite') else {}, pool_pre_ping=True)
if URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def configure(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA busy_timeout=30000')

class Base(DeclarativeBase):
    pass

Session = sessionmaker(engine, expire_on_commit=False)

def get_db():
    with Session() as db:
        yield db
