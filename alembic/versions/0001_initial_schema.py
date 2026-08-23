"""Initial schema with users and documents tables

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-08-23 23:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    op.create_table(
        'documents',
        sa.Column('document_id', sa.String(length=64), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('chunks_count', sa.Integer(), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('owner_id', sa.String(length=100), nullable=False),
        sa.Column('file_extension', sa.String(length=20), nullable=False),
        sa.Column('source_sha256', sa.String(length=64), nullable=False),
        sa.Column('source_size_bytes', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('document_id'),
    )
    op.create_index(op.f('ix_documents_owner_id'), 'documents', ['owner_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_documents_owner_id'), table_name='documents')
    op.drop_table('documents')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_table('users')
