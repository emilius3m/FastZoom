"""Add geographic maps tables

Revision ID: add_geographic_maps_tables
Revises: create_hierarchical_iccd_system
Create Date: 2024-09-30 10:22:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

# revision identifiers
revision = 'add_geographic_maps_tables'
down_revision = 'create_hierarchical_iccd_system'
branch_labels = None
depends_on = None

def upgrade():
    # Geographic Maps table
    op.create_table('geographic_maps',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('site_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('bounds_north', sa.Float(), nullable=False),
        sa.Column('bounds_south', sa.Float(), nullable=False),
        sa.Column('bounds_east', sa.Float(), nullable=False),
        sa.Column('bounds_west', sa.Float(), nullable=False),
        sa.Column('center_lat', sa.Float(), nullable=False),
        sa.Column('center_lng', sa.Float(), nullable=False),
        sa.Column('default_zoom', sa.Integer(), nullable=True),
        sa.Column('map_config', JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['site_id'], ['archaeological_sites.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_geographic_maps_id'), 'geographic_maps', ['id'], unique=False)

    # Geographic Map Layers table
    op.create_table('geographic_map_layers',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('map_id', UUID(as_uuid=True), nullable=False),
        sa.Column('site_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('layer_type', sa.String(length=100), nullable=True),
        sa.Column('geojson_data', JSON(), nullable=False),
        sa.Column('features_count', sa.Integer(), nullable=True),
        sa.Column('style_config', JSON(), nullable=True),
        sa.Column('is_visible', sa.Boolean(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=True),
        sa.Column('bounds_north', sa.Float(), nullable=True),
        sa.Column('bounds_south', sa.Float(), nullable=True),
        sa.Column('bounds_east', sa.Float(), nullable=True),
        sa.Column('bounds_west', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['map_id'], ['geographic_maps.id'], ),
        sa.ForeignKeyConstraint(['site_id'], ['archaeological_sites.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_geographic_map_layers_id'), 'geographic_map_layers', ['id'], unique=False)

    # Geographic Map Markers table
    op.create_table('geographic_map_markers',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('map_id', UUID(as_uuid=True), nullable=False),
        sa.Column('site_id', UUID(as_uuid=True), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('marker_type', sa.String(length=100), nullable=True),
        sa.Column('icon', sa.String(length=10), nullable=True),
        sa.Column('color', sa.String(length=20), nullable=True),
        sa.Column('metadata', JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['map_id'], ['geographic_maps.id'], ),
        sa.ForeignKeyConstraint(['site_id'], ['archaeological_sites.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_geographic_map_markers_id'), 'geographic_map_markers', ['id'], unique=False)

    # Geographic Map Marker Photos association table
    op.create_table('geographic_map_marker_photos',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('marker_id', UUID(as_uuid=True), nullable=False),
        sa.Column('photo_id', UUID(as_uuid=True), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=True),
        sa.Column('is_primary', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_by', UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['marker_id'], ['geographic_map_markers.id'], ),
        sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_geographic_map_marker_photos_id'), 'geographic_map_marker_photos', ['id'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_geographic_map_marker_photos_id'), table_name='geographic_map_marker_photos')
    op.drop_table('geographic_map_marker_photos')
    op.drop_index(op.f('ix_geographic_map_markers_id'), table_name='geographic_map_markers')
    op.drop_table('geographic_map_markers')
    op.drop_index(op.f('ix_geographic_map_layers_id'), table_name='geographic_map_layers')
    op.drop_table('geographic_map_layers')
    op.drop_index(op.f('ix_geographic_maps_id'), table_name='geographic_maps')
    op.drop_table('geographic_maps')