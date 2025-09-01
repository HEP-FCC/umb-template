-- Extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm; -- for fuzzy string matching (trigram similarity)

-- Helper functions
-- This function concatenates all values of a JSONB object into a single string,
-- which can then be indexed for full-text search.
CREATE OR REPLACE FUNCTION jsonb_values_to_text(jsonb_in JSONB)
RETURNS TEXT LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
    RETURN (SELECT string_agg(value, ' ') FROM jsonb_each_text(jsonb_in));
END;
$$;

-- Navigation tables (lookup tables for categorical data)
-- These are example navigation entities - customize these for your domain
CREATE TABLE IF NOT EXISTS categories (
    category_id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS types (
    type_id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sources (
    source_id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS statuses (
    status_id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Example: formats table for file/data format classification
CREATE TABLE IF NOT EXISTS formats (
    format_id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Main entities table (this is your main entity table - customize for your domain)
CREATE TABLE IF NOT EXISTS entities (
    entity_id BIGSERIAL PRIMARY KEY,
    uuid UUID UNIQUE NOT NULL,
    name TEXT NOT NULL,
    -- Foreign key relationships with proper constraints
    category_id INTEGER REFERENCES categories(category_id) ON DELETE SET NULL,
    type_id INTEGER REFERENCES types(type_id) ON DELETE SET NULL,
    source_id INTEGER REFERENCES sources(source_id) ON DELETE SET NULL,
    status_id INTEGER REFERENCES statuses(status_id) ON DELETE SET NULL,
    format_id INTEGER REFERENCES formats(format_id) ON DELETE SET NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    last_edited_at TIMESTAMPTZ DEFAULT NULL,
    edited_by_name TEXT DEFAULT NULL,

    -- Add constraints for data integrity
    CONSTRAINT chk_name_not_empty CHECK (length(trim(name)) > 0),
    CONSTRAINT chk_edited_at_after_created CHECK (last_edited_at IS NULL OR last_edited_at >= created_at),
    CONSTRAINT chk_updated_at_after_created CHECK (updated_at >= created_at),
    CONSTRAINT chk_metadata_valid CHECK (metadata IS NULL OR jsonb_typeof(metadata) = 'object')
);

-- Indexes
-- Standard B-tree indexes for foreign keys to speed up joins
CREATE INDEX IF NOT EXISTS idx_entities_uuid ON entities(uuid);
CREATE INDEX IF NOT EXISTS idx_entities_category_id ON entities(category_id);
CREATE INDEX IF NOT EXISTS idx_entities_type_id ON entities(type_id);
CREATE INDEX IF NOT EXISTS idx_entities_source_id ON entities(source_id);
CREATE INDEX IF NOT EXISTS idx_entities_status_id ON entities(status_id);
CREATE INDEX IF NOT EXISTS idx_entities_format_id ON entities(format_id);

-- GIN (Generalized Inverted Index) with trigram operations for fast fuzzy search and ILIKE/regex
CREATE INDEX IF NOT EXISTS idx_categories_name_gin ON categories USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_types_name_gin ON types USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_sources_name_gin ON sources USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_statuses_name_gin ON statuses USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_formats_name_gin ON formats USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_entities_name_gin ON entities USING GIN (name gin_trgm_ops);

-- GIN index on an expression to enable fast fuzzy search on JSONB values
CREATE INDEX IF NOT EXISTS idx_entities_metadata_search_gin ON entities USING GIN (jsonb_values_to_text(metadata) gin_trgm_ops);

-- Additional JSONB indexes for metadata search optimization
-- Full JSONB index for containment queries (e.g., searching for specific key-value pairs)
CREATE INDEX IF NOT EXISTS idx_entities_metadata_gin ON entities USING GIN (metadata);

-- Optimized JSONB index for path-based queries (smaller, faster for specific patterns)
CREATE INDEX IF NOT EXISTS idx_entities_metadata_path_gin ON entities USING GIN (metadata jsonb_path_ops);

-- Specific indexes for commonly searched metadata fields (customize for your JSON structure)
-- These will be much faster for queries targeting specific metadata fields
CREATE INDEX IF NOT EXISTS idx_entities_metadata_description ON entities USING GIN ((metadata->>'description') gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_entities_metadata_comment ON entities USING GIN ((metadata->>'comment') gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_entities_metadata_category ON entities USING BTREE ((metadata->>'category'));
CREATE INDEX IF NOT EXISTS idx_entities_metadata_type ON entities USING BTREE ((metadata->>'type'));
CREATE INDEX IF NOT EXISTS idx_entities_metadata_source ON entities USING BTREE ((metadata->>'source'));
CREATE INDEX IF NOT EXISTS idx_entities_metadata_status ON entities USING BTREE ((metadata->>'status'));

-- Temporal indexes for sorting and filtering by timestamps
CREATE INDEX IF NOT EXISTS idx_entities_created_at ON entities(created_at);
CREATE INDEX IF NOT EXISTS idx_entities_updated_at ON entities(updated_at);
CREATE INDEX IF NOT EXISTS idx_entities_last_edited_at ON entities(last_edited_at);
CREATE INDEX IF NOT EXISTS idx_entities_created_at_desc ON entities(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_entities_updated_at_desc ON entities(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_entities_last_edited_at_desc ON entities(last_edited_at DESC);

-- Composite indexes for common query patterns
-- This supports pagination and sorting by last_edited_at which is common in your app
CREATE INDEX IF NOT EXISTS idx_entities_edited_id_composite ON entities(last_edited_at DESC, entity_id);

-- Index for efficient counting and existence checks
CREATE INDEX IF NOT EXISTS idx_entities_name_lower ON entities(LOWER(name));

-- Partial indexes for active/completed entities (if status filtering is common)
CREATE INDEX IF NOT EXISTS idx_entities_status_active ON entities(entity_id)
WHERE metadata->>'status' = 'Active';

-- Partial index for entities with metadata (excludes NULL metadata)
CREATE INDEX IF NOT EXISTS idx_entities_with_metadata ON entities(entity_id)
WHERE metadata IS NOT NULL;

-- Performance optimization: Set statistics targets for better query planning
-- Increase statistics for frequently queried columns
ALTER TABLE entities ALTER COLUMN name SET STATISTICS 1000;
ALTER TABLE entities ALTER COLUMN metadata SET STATISTICS 1000;
ALTER TABLE entities ALTER COLUMN updated_at SET STATISTICS 500;
ALTER TABLE entities ALTER COLUMN last_edited_at SET STATISTICS 500;

-- Set statistics for lookup tables
ALTER TABLE categories ALTER COLUMN name SET STATISTICS 100;
ALTER TABLE types ALTER COLUMN name SET STATISTICS 100;
ALTER TABLE sources ALTER COLUMN name SET STATISTICS 100;
ALTER TABLE statuses ALTER COLUMN name SET STATISTICS 100;
ALTER TABLE formats ALTER COLUMN name SET STATISTICS 100;
