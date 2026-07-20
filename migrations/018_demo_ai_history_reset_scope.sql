CREATE OR REPLACE FUNCTION heatgrid_admin.reset_demo_ai_history()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $reset_demo_ai_history$
BEGIN
    TRUNCATE TABLE
        public.agent_runs,
        public.incident_document_versions,
        public.operation_idempotency_keys
    CASCADE;
END;
$reset_demo_ai_history$;

ALTER FUNCTION heatgrid_admin.reset_demo_ai_history() OWNER TO CURRENT_USER;
REVOKE ALL ON FUNCTION heatgrid_admin.reset_demo_ai_history() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION heatgrid_admin.reset_demo_ai_history() TO heatgrid_app;

COMMENT ON FUNCTION heatgrid_admin.reset_demo_ai_history() IS
    'Demo-only reset for AI runs, incident documents, and their idempotency records; operational source data and operations reports are preserved.';
