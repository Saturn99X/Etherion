-- Enable Row-Level Security (RLS) per table that has a tenant_id column
-- Assumptions:
-- - Custom GUC app.tenant_id is set by the app per-connection (see src/database/db.py)
-- - Current database is the application DB
-- - Connected role owns the target tables or has sufficient privileges to alter them

DO $$
DECLARE
    r RECORD;
    v_schema text := 'public';
BEGIN
    FOR r IN (
        SELECT table_schema, table_name
        FROM information_schema.columns
        WHERE column_name = 'tenant_id'
          AND table_schema = v_schema
          AND table_name NOT IN ('alembic_version')  -- Exclude migration metadata
        GROUP BY table_schema, table_name
        ORDER BY table_schema, table_name
    ) LOOP
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', r.table_schema, r.table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', r.table_schema, r.table_name);

        -- SELECT policy (visible rows must match tenant_id)
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = r.table_schema
              AND tablename  = r.table_name
              AND policyname = 'tenant_select'
        ) THEN
            EXECUTE format(
                'CREATE POLICY tenant_select ON %I.%I FOR SELECT USING ((tenant_id)::text = current_setting(''app.tenant_id'', true))',
                r.table_schema, r.table_name
            );
        END IF;

        -- INSERT/UPDATE/DELETE policy (written rows must match tenant_id)
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = r.table_schema
              AND tablename  = r.table_name
              AND policyname = 'tenant_write'
        ) THEN
            EXECUTE format(
                'CREATE POLICY tenant_write ON %I.%I FOR ALL USING ((tenant_id)::text = current_setting(''app.tenant_id'', true)) WITH CHECK ((tenant_id)::text = current_setting(''app.tenant_id'', true))',
                r.table_schema, r.table_name
            );
        END IF;
    END LOOP;
END$$;

-- Optional: verify policies per table
-- SELECT schemaname, tablename, policyname, cmd, qual, with_check FROM pg_policies ORDER BY 1,2,3;
