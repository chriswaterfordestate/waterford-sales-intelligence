"""016 session hotfixes — MCR, client_ownership, classify fixes, DLIB alias"""
from alembic import op

revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None

def upgrade():
    import os
    sql_path = os.path.join(os.path.dirname(__file__), '016_session_hotfixes.sql')
    with open(sql_path) as f:
        op.execute(f.read())

def downgrade():
    pass  # Hotfixes are not reversible via migration
