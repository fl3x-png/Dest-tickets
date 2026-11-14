"""Initial stage-one schema. Frozen metadata lives in this migration."""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('users', sa.Column('id',sa.Integer,primary_key=True),sa.Column('username',sa.String(100),nullable=False,unique=True),sa.Column('name',sa.String(150),nullable=False),sa.Column('password_hash',sa.Text,nullable=False),sa.Column('role',sa.String(20),nullable=False),sa.Column('active',sa.Boolean,nullable=False),sa.CheckConstraint("role IN ('admin','manager')"))
    op.create_table('sessions',sa.Column('id',sa.String(64),primary_key=True),sa.Column('user_id',sa.Integer,sa.ForeignKey('users.id'),nullable=False),sa.Column('csrf',sa.String(64),nullable=False),sa.Column('expires',sa.Integer,nullable=False))
    op.create_table('login_attempts',sa.Column('key',sa.String(64),primary_key=True),sa.Column('count',sa.Integer,nullable=False),sa.Column('until',sa.Integer,nullable=False))
    op.create_table('events',sa.Column('id',sa.Integer,primary_key=True),*[sa.Column(k,sa.String(n),nullable=False) for k,n in [('title',200),('city',100),('date',10),('time',5),('address',300),('venue',200),('speaker',150),('status',20)]],sa.Column('created_at',sa.String,nullable=False),sa.Column('capacity',sa.Integer),sa.Column('next_number',sa.Integer,nullable=False),sa.CheckConstraint("status IN ('draft','open','closed','completed')"),sa.CheckConstraint('next_number > 0'))
    op.create_table('registrations',sa.Column('id',sa.Integer,primary_key=True),sa.Column('event_id',sa.Integer,sa.ForeignKey('events.id'),nullable=False),sa.Column('phone',sa.String(30)),sa.Column('created_by',sa.Integer,sa.ForeignKey('users.id'),nullable=False),sa.Column('created_at',sa.String,nullable=False),*[sa.Column(k,sa.String(100)) for k in ['bitrix_lead_id','bitrix_contact_id','external_registration_id']])
    op.create_table('issue_batches',sa.Column('key',sa.String(100),primary_key=True),sa.Column('fingerprint',sa.String(64),nullable=False),sa.Column('created_by',sa.Integer,sa.ForeignKey('users.id'),nullable=False),sa.Column('registration_id',sa.Integer,sa.ForeignKey('registrations.id'),nullable=False))
    op.create_table('tickets',sa.Column('id',sa.Integer,primary_key=True),sa.Column('event_id',sa.Integer,sa.ForeignKey('events.id'),nullable=False),sa.Column('registration_id',sa.Integer,sa.ForeignKey('registrations.id'),nullable=False),sa.Column('batch_key',sa.String(100),sa.ForeignKey('issue_batches.key'),nullable=False),sa.Column('number',sa.Integer,nullable=False),sa.Column('name',sa.String(200),nullable=False),sa.Column('created_by',sa.Integer,sa.ForeignKey('users.id'),nullable=False),sa.Column('created_at',sa.String,nullable=False),sa.Column('cancelled',sa.Boolean,nullable=False),sa.Column('snapshot',sa.JSON,nullable=False),sa.UniqueConstraint('event_id','number'),sa.CheckConstraint('number > 0'))
    op.create_table('audit_logs',sa.Column('id',sa.Integer,primary_key=True),sa.Column('user_id',sa.Integer,sa.ForeignKey('users.id'),nullable=False),sa.Column('action',sa.String(100),nullable=False),sa.Column('entity_id',sa.Integer,nullable=False),sa.Column('detail',sa.Text,nullable=False),sa.Column('created_at',sa.String,nullable=False))
    for table, columns in [('registrations',['event_id']),('tickets',['event_id','registration_id','batch_key','name']),('audit_logs',['entity_id'])]:
        for col in columns: op.create_index(f'ix_{table}_{col}',table,[col])

def downgrade():
    for table in ['audit_logs','tickets','issue_batches','registrations','events','login_attempts','sessions','users']: op.drop_table(table)
