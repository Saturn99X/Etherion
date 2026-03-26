-- RLS policy application for multi-tenant database
-- Safe/idempotent pattern: create schemas/roles/policies if not exist
-- NOTE: This script is executed inside the VPC via Cloud Run Job 'db-rls-apply'.
-- Database URL is provided via env, and SQL content is supplied via Secret Manager (RLS_SQL_B64).

BEGIN;

-- ============================================================================
-- CRITICAL: Disable RLS on migration metadata tables
-- Alembic needs unrestricted access to track migration state
-- ============================================================================
DO $
BEGIN
  IF to_regclass('public.alembic_version') IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public.alembic_version DISABLE ROW LEVEL SECURITY';
    RAISE NOTICE 'Disabled RLS on alembic_version table';
  END IF;
END$;

-- Example: ensure tenant_id column exists on key tables (adjust as needed)
-- ALTER TABLE public.users ADD COLUMN IF NOT EXISTS tenant_id text;
-- ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS tenant_id text;

-- Schema alignment for threaded messages: ensure new columns exist on public.message
DO $$
BEGIN
  IF to_regclass('public.message') IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public.message ADD COLUMN IF NOT EXISTS message_id varchar(64)';
    EXECUTE 'ALTER TABLE public.message ADD COLUMN IF NOT EXISTS thread_id varchar(64)';
    EXECUTE 'ALTER TABLE public.message ADD COLUMN IF NOT EXISTS parent_id varchar(64)';
    EXECUTE 'ALTER TABLE public.message ADD COLUMN IF NOT EXISTS branch_id varchar(64)';
    EXECUTE 'ALTER TABLE public.message ADD COLUMN IF NOT EXISTS metadata_json text';
  END IF;
END$$;

-- Schema alignment for full fidelity replay (Job and ExecutionTraceStep)
DO $$
BEGIN
  -- 1. Job table updates
  IF to_regclass('public.job') IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public.job ADD COLUMN IF NOT EXISTS thread_id text';
    -- Note: Foreign key and index are handled by Alembic, but we ensure column here for RLS
  END IF;

  -- 2. ExecutionTraceStep table updates
  IF to_regclass('public.executiontracestep') IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public.executiontracestep ADD COLUMN IF NOT EXISTS thread_id text';
    EXECUTE 'ALTER TABLE public.executiontracestep ADD COLUMN IF NOT EXISTS message_id text';
    EXECUTE 'ALTER TABLE public.executiontracestep ADD COLUMN IF NOT EXISTS actor text';
    EXECUTE 'ALTER TABLE public.executiontracestep ADD COLUMN IF NOT EXISTS event_type text';
    EXECUTE 'ALTER TABLE public.executiontracestep ADD COLUMN IF NOT EXISTS span_id text';
    EXECUTE 'ALTER TABLE public.executiontracestep ADD COLUMN IF NOT EXISTS parent_span_id text';
    
    -- Set defaults for existing rows to satisfy NOT NULL constraints if applied later
    EXECUTE 'UPDATE public.executiontracestep SET actor = ''orchestrator'' WHERE actor IS NULL';
    EXECUTE 'UPDATE public.executiontracestep SET event_type = ''unknown'' WHERE event_type IS NULL';
  END IF;
END$$;

-- Create a tenant predicate function if you prefer centralizing logic
-- CREATE OR REPLACE FUNCTION public.current_tenant_id() RETURNS text AS $$
--   SELECT current_setting('request.jwt.tenant_id', true);
-- $$ LANGUAGE sql STABLE;

-- ============================================================================
-- CLEANUP: Drop ALL unsafe Alembic-created 'tenant_isolation' policies
-- These policies use ::integer cast which fails when app.tenant_id is NULL/empty
-- ============================================================================
DO $$
DECLARE
  tables_to_clean TEXT[] := ARRAY[
    'tenant', 'user', 'project', 'toneprofile', 'conversation',
    'projectkbfile', 'message', 'expense', 'executioncost', 'job',
    'customagentdefinition', 'agentteam', 'scheduledtask', 'executiontracestep',
    'thread', 'messageartifact', 'toolinvocation', 'user_settings'
  ];
  tbl TEXT;
BEGIN
  FOREACH tbl IN ARRAY tables_to_clean LOOP
    IF to_regclass('public.' || tbl) IS NOT NULL THEN
      -- Drop the unsafe Alembic policy
      EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON public.%I', tbl);
      RAISE NOTICE 'Dropped tenant_isolation policy from %', tbl;
    END IF;
  END LOOP;
END$$;

-- Enable RLS (idempotent) for new conversation tables and settings
DO $$
BEGIN
  IF to_regclass('public.thread') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM pg_class c
       JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname = 'public'
         AND c.relname = 'thread'
         AND pg_get_userbyid(c.relowner) = current_user
     ) THEN
    EXECUTE 'ALTER TABLE public.thread ENABLE ROW LEVEL SECURITY';
  END IF;
  IF to_regclass('public.message') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM pg_class c
       JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname = 'public'
         AND c.relname = 'message'
         AND pg_get_userbyid(c.relowner) = current_user
     ) THEN
    EXECUTE 'ALTER TABLE public.message ENABLE ROW LEVEL SECURITY';
  END IF;
  IF to_regclass('public.messageartifact') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM pg_class c
       JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname = 'public'
         AND c.relname = 'messageartifact'
         AND pg_get_userbyid(c.relowner) = current_user
     ) THEN
    EXECUTE 'ALTER TABLE public.messageartifact ENABLE ROW LEVEL SECURITY';
  END IF;
  IF to_regclass('public.toolinvocation') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM pg_class c
       JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname = 'public'
         AND c.relname = 'toolinvocation'
         AND pg_get_userbyid(c.relowner) = current_user
     ) THEN
    EXECUTE 'ALTER TABLE public.toolinvocation ENABLE ROW LEVEL SECURITY';
  END IF;
  IF to_regclass('public.user_settings') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM pg_class c
       JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname = 'public'
         AND c.relname = 'user_settings'
         AND pg_get_userbyid(c.relowner) = current_user
     ) THEN
    EXECUTE 'ALTER TABLE public.user_settings ENABLE ROW LEVEL SECURITY';
  END IF;
END$$;

-- Thread: simple tenant_id match
DO $$
BEGIN
  IF to_regclass('public.thread') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM pg_class c
       JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname = 'public'
         AND c.relname = 'thread'
         AND pg_get_userbyid(c.relowner) = current_user
     ) THEN
    EXECUTE 'DROP POLICY IF EXISTS thread_tenant_isolation ON public.thread';
    EXECUTE 'CREATE POLICY thread_tenant_isolation ON public.thread
      USING (tenant_id::text = current_setting(''app.tenant_id'', true))
      WITH CHECK (tenant_id::text = current_setting(''app.tenant_id'', true))';
  END IF;
END$$;

-- Message: join to thread on thread_id for tenant isolation
DO $$
BEGIN
  IF to_regclass('public.message') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM pg_class c
       JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname = 'public'
         AND c.relname = 'message'
         AND pg_get_userbyid(c.relowner) = current_user
     ) THEN
    EXECUTE 'DROP POLICY IF EXISTS message_tenant_isolation ON public.message';
    EXECUTE 'CREATE POLICY message_tenant_isolation ON public.message
      USING (EXISTS (
        SELECT 1 FROM public.thread t
        WHERE t.thread_id = message.thread_id
          AND t.tenant_id::text = current_setting(''app.tenant_id'', true)
      ))
      WITH CHECK (EXISTS (
        SELECT 1 FROM public.thread t
        WHERE t.thread_id = message.thread_id
          AND t.tenant_id::text = current_setting(''app.tenant_id'', true)
      ))';
  END IF;
END$$;

-- MessageArtifact: join to message, which joins to thread
DO $$
BEGIN
  IF to_regclass('public.messageartifact') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM pg_class c
       JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname = 'public'
         AND c.relname = 'messageartifact'
         AND pg_get_userbyid(c.relowner) = current_user
     ) THEN
    EXECUTE 'DROP POLICY IF EXISTS messageartifact_tenant_isolation ON public.messageartifact';
    EXECUTE 'CREATE POLICY messageartifact_tenant_isolation ON public.messageartifact
      USING (EXISTS (
        SELECT 1 FROM public.message m JOIN public.thread t ON t.thread_id = m.thread_id
        WHERE m.message_id = messageartifact.message_id
          AND t.tenant_id::text = current_setting(''app.tenant_id'', true)
      ))
      WITH CHECK (EXISTS (
        SELECT 1 FROM public.message m JOIN public.thread t ON t.thread_id = m.thread_id
        WHERE m.message_id = messageartifact.message_id
          AND t.tenant_id::text = current_setting(''app.tenant_id'', true)
      ))';
  END IF;
END$$;

-- ToolInvocation: join to thread via thread_id
DO $$
BEGIN
  IF to_regclass('public.toolinvocation') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM pg_class c
       JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname = 'public'
         AND c.relname = 'toolinvocation'
         AND pg_get_userbyid(c.relowner) = current_user
     ) THEN
    EXECUTE 'DROP POLICY IF EXISTS toolinvocation_tenant_isolation ON public.toolinvocation';
    EXECUTE 'CREATE POLICY toolinvocation_tenant_isolation ON public.toolinvocation
      USING (EXISTS (
        SELECT 1 FROM public.thread t
        WHERE t.thread_id = toolinvocation.thread_id
          AND t.tenant_id::text = current_setting(''app.tenant_id'', true)
      ))
      WITH CHECK (EXISTS (
        SELECT 1 FROM public.thread t
        WHERE t.thread_id = toolinvocation.thread_id
          AND t.tenant_id::text = current_setting(''app.tenant_id'', true)
      ))';
  END IF;
END$$;

-- User settings: tenant_id match
DO $$
BEGIN
  IF to_regclass('public.user_settings') IS NOT NULL
     AND EXISTS (
       SELECT 1
       FROM pg_class c
       JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE n.nspname = 'public'
         AND c.relname = 'user_settings'
         AND pg_get_userbyid(c.relowner) = current_user
     ) THEN
    EXECUTE 'DROP POLICY IF EXISTS usersettings_tenant_isolation ON public.user_settings';
    EXECUTE 'CREATE POLICY usersettings_tenant_isolation ON public.user_settings
      USING (tenant_id::text = current_setting(''app.tenant_id'', true))
      WITH CHECK (tenant_id::text = current_setting(''app.tenant_id'', true))';
  END IF;
END$$;

-- Job: tenant_id match - with explicit debug and policy replacement
DO $$
BEGIN
  IF to_regclass('public.job') IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public.job ENABLE ROW LEVEL SECURITY';
    
    -- Drop all existing policies to start fresh
    EXECUTE 'DROP POLICY IF EXISTS tenant_isolation ON public.job';
    EXECUTE 'DROP POLICY IF EXISTS job_tenant_isolation ON public.job';
    
    -- Create policy: allow if tenant_id matches app.tenant_id
    EXECUTE 'CREATE POLICY job_tenant_isolation ON public.job
      USING (tenant_id::text = current_setting(''app.tenant_id'', true))
      WITH CHECK (tenant_id::text = current_setting(''app.tenant_id'', true))';
    
    RAISE NOTICE 'Job RLS policy created successfully.';
  ELSE
    RAISE NOTICE 'Table public.job not found!';
  END IF;
END$$;

-- ============================================================================
-- Create safe RLS policies for all other tenant-aware tables
-- These replace the unsafe Alembic policies and use text comparison
-- ============================================================================
DO $$
DECLARE
  simple_tenant_tables TEXT[] := ARRAY[
    'project', 'toneprofile', 'conversation', 'projectkbfile',
    'expense', 'executioncost', 'customagentdefinition', 'agentteam',
    'scheduledtask', 'executiontracestep'
  ];
  tbl TEXT;
BEGIN
  FOREACH tbl IN ARRAY simple_tenant_tables LOOP
    IF to_regclass('public.' || tbl) IS NOT NULL THEN
      -- Enable RLS
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', tbl);
      
      -- Drop any existing policy
      EXECUTE format('DROP POLICY IF EXISTS %I_tenant_isolation ON public.%I', tbl, tbl);
      
      -- Create safe policy with text comparison
      EXECUTE format('CREATE POLICY %I_tenant_isolation ON public.%I
        USING (tenant_id::text = current_setting(''app.tenant_id'', true))
        WITH CHECK (tenant_id::text = current_setting(''app.tenant_id'', true))', tbl, tbl);
      
      RAISE NOTICE 'Created safe RLS policy for %', tbl;
    END IF;
  END LOOP;
END$$;

-- Tenant RLS: Allow INSERT during onboarding, and SELECT for own tenant OR specific subdomain check
DO $$
BEGIN
  IF to_regclass('public.tenant') IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public.tenant ENABLE ROW LEVEL SECURITY';
    
    -- 1. INSERT: Allow if no tenant context is set (onboarding)
    EXECUTE 'DROP POLICY IF EXISTS tenant_onboarding_insert ON public.tenant';
    EXECUTE 'CREATE POLICY tenant_onboarding_insert ON public.tenant
      AS PERMISSIVE
      FOR INSERT
      WITH CHECK (
        current_setting(''app.tenant_id'', true) IS NULL 
        OR 
        current_setting(''app.tenant_id'', true) = ''''
      )';

    -- 2. SELECT: Allow if ID matches tenant context OR if checking specific subdomain during onboarding
    EXECUTE 'DROP POLICY IF EXISTS tenant_isolation ON public.tenant';
    EXECUTE 'DROP POLICY IF EXISTS tenant_select ON public.tenant';
    EXECUTE 'CREATE POLICY tenant_select ON public.tenant
      AS PERMISSIVE
      FOR SELECT
      USING (
        id::text = current_setting(''app.tenant_id'', true)
        OR
        (
          (current_setting(''app.tenant_id'', true) IS NULL OR current_setting(''app.tenant_id'', true) = '''')
          AND 
          subdomain = current_setting(''app.requested_subdomain'', true)
        )
      )';
      
    RAISE NOTICE 'Tenant policies created successfully.';
  ELSE
    RAISE NOTICE 'Table public.tenant not found!';
  END IF;
END$$;

-- User RLS: Fix the unsafe ::integer cast from the original Alembic migration
-- Allow SELECT/INSERT/UPDATE/DELETE only when tenant_id matches, with safe NULL/empty handling
DO $$
BEGIN
  IF to_regclass('public.user') IS NOT NULL THEN
    EXECUTE 'ALTER TABLE public."user" ENABLE ROW LEVEL SECURITY';
    
    -- Drop the unsafe Alembic-created policy
    EXECUTE 'DROP POLICY IF EXISTS tenant_isolation ON public."user"';
    
    -- Drop our policy if it exists (for idempotency)
    EXECUTE 'DROP POLICY IF EXISTS user_tenant_isolation ON public."user"';
    
    -- Create a safe policy that handles NULL and empty string
    EXECUTE 'CREATE POLICY user_tenant_isolation ON public."user"
      AS PERMISSIVE
      FOR ALL
      USING (
        tenant_id::text = current_setting(''app.tenant_id'', true)
        OR
        current_setting(''app.tenant_id'', true) IS NULL
        OR
        current_setting(''app.tenant_id'', true) = ''''
      )
      WITH CHECK (
        tenant_id::text = current_setting(''app.tenant_id'', true)
        OR
        current_setting(''app.tenant_id'', true) IS NULL
        OR
        current_setting(''app.tenant_id'', true) = ''''
      )';
      
    RAISE NOTICE 'User table RLS policy fixed successfully.';
  END IF;
END$$;

-- Verify policies
SELECT tablename, policyname FROM pg_policies WHERE tablename = 'tenant';

-- DROP POLICY IF EXISTS tenant_isolation_documents ON public.documents;
-- CREATE POLICY tenant_isolation_documents ON public.documents
--   USING (tenant_id = current_setting('app.tenant_id', true))
--   WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- Optional: more granular roles/policies per service account/role

COMMIT;

-- Guidance:
-- 1) Set app.tenant_id per session before queries OR implement a SECURITY DEFINER function
--    that validates tokens and sets the GUC.
-- 2) Align with your application’s RLS middleware so it sets the right GUC per request.
