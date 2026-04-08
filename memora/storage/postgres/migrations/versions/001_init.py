"""Initial migration for MEMORA PostgreSQL schema.

Creates exactly 4 tables as per spec: mem_cubes, quarantine_records, failure_log, timeline_events.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '001_init'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the initial database schema."""
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    
    # Create mem_cubes table
    op.create_table('mem_cubes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('uuid_generate_v4()'), primary_key=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('memory_type', sa.String(length=20), nullable=False),
        sa.Column('tier', sa.String(length=10), nullable=False),
        sa.Column('tags', postgresql.JSON(astext_type=sa.Text()), nullable=False, default=sa.text("'[]'::json")),
        sa.Column('embedding', postgresql.VECTOR(384), nullable=True),
        sa.Column('provenance', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('access_count', sa.Integer(), nullable=False, default=sa.text('0')),
        sa.Column('ttl_seconds', sa.Integer(), nullable=True),
        sa.Column('extra', postgresql.JSON(astext_type=sa.Text()), nullable=False, default=sa.text("'{}'::json")),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()'))
    )
    
    # Create indexes for mem_cubes
    op.create_index('mem_cubes_type_idx', 'mem_cubes', ['memory_type'])
    op.create_index('mem_cubes_tier_idx', 'mem_cubes', ['tier'])
    op.create_index('mem_cubes_tags_idx', 'mem_cubes', ['tags'], postgresql_using='gin')
    op.create_index('mem_cubes_embedding_idx', 'mem_cubes', ['embedding'], postgresql_using='ivfflat', postgresql_ops={'embedding': 'vector_cosine_ops'})
    
    # Create quarantine_records table
    op.create_table('quarantine_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('uuid_generate_v4()'), primary_key=True),
        sa.Column('incoming_cube_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('conflicting_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contradiction_score', sa.Float(), nullable=False),
        sa.Column('reasoning', sa.Text(), nullable=False),
        sa.Column('suggested_resolution', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('merged_content', sa.Text(), nullable=True),
        sa.Column('incoming_cube_json', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('resolved_at', sa.DateTime(), nullable=True)
    )
    
    # Create failure_log table
    op.create_table('failure_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('uuid_generate_v4()'), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action_description', sa.Text(), nullable=False),
        sa.Column('memory_cluster_ids', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('feedback', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()'))
    )
    
    # Create index for failure_log
    op.create_index('failure_log_session_idx', 'failure_log', ['session_id'])
    
    # Create timeline_events table
    op.create_table('timeline_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('uuid_generate_v4()'), primary_key=True),
        sa.Column('cube_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('event_type', sa.String(length=30), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=False, default=sa.text("'{}'::json")),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()'))
    )
    
    # Create indexes for timeline_events
    op.create_index('timeline_session_idx', 'timeline_events', ['session_id'])
    op.create_index('timeline_created_idx', 'timeline_events', ['created_at'], postgresql_using='btree')


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    # Drop indexes first
    op.drop_index('timeline_created_idx', table_name='timeline_events')
    op.drop_index('timeline_session_idx', table_name='timeline_events')
    op.drop_index('failure_log_session_idx', table_name='failure_log')
    op.drop_index('mem_cubes_embedding_idx', table_name='mem_cubes')
    op.drop_index('mem_cubes_tags_idx', table_name='mem_cubes')
    op.drop_index('mem_cubes_tier_idx', table_name='mem_cubes')
    op.drop_index('mem_cubes_type_idx', table_name='mem_cubes')
    
    # Drop tables
    op.drop_table('timeline_events')
    op.drop_table('failure_log')
    op.drop_table('quarantine_records')
    op.drop_table('mem_cubes')
    
    # Drop pgvector extension
    op.execute("DROP EXTENSION IF EXISTS vector")
