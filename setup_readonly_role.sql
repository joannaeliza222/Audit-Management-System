-- 
-- Read-Only PostgreSQL Role Setup for Ask Your Database Feature
-- 
-- SECURITY CRITICAL: This script creates a read-only database role that can only
-- execute SELECT queries. This role must be used for all natural language SQL
-- query execution to prevent data modification.
--
-- IMPORTANT: Run this script as a PostgreSQL superuser (e.g., postgres)
--

-- Create the read-only role
CREATE ROLE ams_readonly WITH LOGIN PASSWORD 'CHANGE_THIS_PASSWORD';

-- Grant CONNECT on the database
GRANT CONNECT ON DATABASE ams_db TO ams_readonly;

-- Grant USAGE on schema
GRANT USAGE ON SCHEMA public TO ams_readonly;

-- Grant SELECT on all existing tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ams_readonly;

-- Grant SELECT on all future tables (via default privileges)
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO ams_readonly;

-- Grant SELECT on all existing sequences (needed for some queries)
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO ams_readonly;

-- Grant SELECT on all future sequences
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO ams_readonly;

-- 
-- IMPORTANT: Add the following to your .env file:
-- READ_ONLY_DB_URI=postgresql://ams_readonly:CHANGE_THIS_PASSWORD@localhost:5432/ams_db
--
-- Then change the password 'CHANGE_THIS_PASSWORD' to a strong, secure password.
-- 

-- 
-- To revoke access if needed:
-- REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM ams_readonly;
-- REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM ams_readonly;
-- REVOKE USAGE ON SCHEMA public FROM ams_readonly;
-- REVOKE CONNECT ON DATABASE ams_db FROM ams_readonly;
-- DROP ROLE ams_readonly;
--
