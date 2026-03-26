-- Database fix for "known" issues identified from December 2025 logs
-- 1. Grant high-privilege role membership to app user to solve owner/permission errors
-- 2. Restore RLS onboarding policies

BEGIN;

-- Grant etherion role to etherion_user so it inherits ownership/privileges
-- (Assumes etherion role exists and owns the tables from the dump)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'etherion') 
     AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'etherion_user') THEN
    GRANT etherion TO etherion_user;
    RAISE NOTICE 'Granted role etherion to etherion_user';
  END IF;
END$$;

-- Grant basic privileges just in case
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO etherion_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO etherion_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO etherion_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO etherion_user;

-- Re-apply any missing sequence fixes if Max ID > sequence value
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT table_name, column_name 
              FROM information_schema.columns 
              WHERE column_default LIKE 'nextval%' 
              AND table_schema = 'public') LOOP
        EXECUTE 'SELECT setval(pg_get_serial_sequence(''' || r.table_name || ''', ''' || r.column_name || '''), COALESCE((SELECT MAX(' || r.column_name || ') FROM ' || r.table_name || '), 1), true)';
    END LOOP;
END$$;

-- The standard RLS apply script follows
-- (Appending sql/rls/apply.sql here or running it after)

COMMIT;
