from sqlalchemy import create_engine, Column, Integer, String, MetaData
from alembic import op
import sqlalchemy as sa
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import settings

def upgrade():
    # 添加状态字段和任务ID字段
    op.add_column('ppt_files', sa.Column('status', sa.String(), nullable=True))
    op.add_column('ppt_files', sa.Column('task_id', sa.String(), nullable=True))
    op.add_column('ppt_files', sa.Column('error_message', sa.String(), nullable=True))
    
    # 更新现有记录的状态
    connection = op.get_bind()
    connection.execute("UPDATE ppt_files SET status = 'completed' WHERE file_size IS NOT NULL AND file_size > 1024")
    connection.execute("UPDATE ppt_files SET status = 'pending' WHERE status IS NULL")

def downgrade():
    # 删除添加的列
    op.drop_column('ppt_files', 'error_message')
    op.drop_column('ppt_files', 'task_id')
    op.drop_column('ppt_files', 'status')

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade()
    else:
        upgrade()
