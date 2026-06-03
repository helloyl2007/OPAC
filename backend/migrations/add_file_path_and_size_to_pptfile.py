from sqlalchemy import create_engine, Column, Integer, String, MetaData
from alembic import op
import sqlalchemy as sa
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.config import settings

def upgrade():
    # 添加file_path和file_size列
    op.add_column('ppt_files', sa.Column('file_path', sa.String(), nullable=True))
    op.add_column('ppt_files', sa.Column('file_size', sa.Integer(), nullable=True))
    
    # 更新现有记录的file_path
    connection = op.get_bind()
    for row in connection.execute('SELECT id, filename FROM ppt_files'):
        ppt_id, filename = row
        file_path = f"generated/ppts/{filename}"
        connection.execute(f"UPDATE ppt_files SET file_path = '{file_path}' WHERE id = {ppt_id}")
    
    # 设置file_path为非空约束
    op.alter_column('ppt_files', 'file_path', nullable=False)

def downgrade():
    # 删除添加的列
    op.drop_column('ppt_files', 'file_size')
    op.drop_column('ppt_files', 'file_path')

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade()
    else:
        upgrade()
