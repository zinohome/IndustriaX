-- Initialize PostgreSQL extensions for IndustriaX
-- Apache AGE image (PG16) provides age; pgvector must be installed separately
-- if the image includes it; otherwise install via pg_vector extension package.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
