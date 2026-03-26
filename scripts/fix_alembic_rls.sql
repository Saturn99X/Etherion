-- ONE-TIME FIX: Disable RLS on alembic_version table
-- 
-- PROBLEM: Cloud SQL's postgres user doesn't have BYPASSRLS attribute,
-- so when RLS is enabled on alembic_version, migrations fail with
-- "permission denied for table alembic_version"
--
-- SOLUTION: Run this script manually using Cloud SQL Studio or
-- a direct connection to disable RLS on the alembic_version table.
--
-- HOW TO RUN:
-- 1. Go to Cloud Console > SQL > etherion-prod-db > Cloud SQL Studio
-- 2. Connect as postgres user
-- 3. Run this script
--
-- OR use gcloud with IP allowlisting:
-- gcloud sql connect etherion-prod-db --user=postgres --database=etherion_prod_db
-- Then paste this script

-- Check current RLS status
SELECT 
    relname as table_name,
    relrowsecurity as rls_enabled,
    relforcerowsecurity as rls_forced
FROM pg_class 
WHERE relname = 'alembic_version';

-- Disable RLS on alembic_version
ALTER TABLE IF EXISTS alembic_version DISABLE ROW LEVEL SECURITY;

-- Also remove FORCE (in case it was set)
ALTER TABLE IF EXISTS alembic_version NO FORCE ROW LEVEL SECURITY;

-- Drop any policies that might exist
DROP POLICY IF EXISTS tenant_select ON alembic_version;
DROP POLICY IF EXISTS tenant_write ON alembic_version;
DROP POLICY IF EXISTS tenant_isolation ON alembic_version;

-- Verify the fix
SELECT 
    relname as table_name,
    relrowsecurity as rls_enabled,
    relforcerowsecurity as rls_forced
FROM pg_class 
WHERE relname = 'alembic_version';

-- Expected output after fix:
-- table_name       | rls_enabled | rls_forced
-- -----------------+-------------+------------
-- alembic_version  | false       | false
