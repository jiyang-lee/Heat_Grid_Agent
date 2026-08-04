CREATE SCHEMA IF NOT EXISTS heatgrid_admin AUTHORIZATION CURRENT_USER;
ALTER SCHEMA heatgrid_admin OWNER TO CURRENT_USER;

REVOKE ALL ON SCHEMA heatgrid_admin FROM PUBLIC;
REVOKE CREATE ON SCHEMA heatgrid_admin FROM heatgrid_app;
GRANT USAGE ON SCHEMA heatgrid_admin TO heatgrid_app;

CREATE OR REPLACE FUNCTION heatgrid_admin.reset_demo_ai_history()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $reset_demo_ai_history$
BEGIN
    TRUNCATE TABLE public.agent_runs CASCADE;
END;
$reset_demo_ai_history$;

ALTER FUNCTION heatgrid_admin.reset_demo_ai_history() OWNER TO CURRENT_USER;
REVOKE ALL ON FUNCTION heatgrid_admin.reset_demo_ai_history() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION heatgrid_admin.reset_demo_ai_history() TO heatgrid_app;

COMMENT ON FUNCTION heatgrid_admin.reset_demo_ai_history() IS
    'Demo-only privileged reset entry point; HTTP access remains feature-flagged.';
