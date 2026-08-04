COMMENT ON SCHEMA public IS 'HeatGrid schema frozen at version 013';

ALTER TABLE public.agent_stage_snapshots
    DROP CONSTRAINT agent_stage_snapshots_score_contract;

ALTER TABLE public.agent_stage_snapshots
    ADD CONSTRAINT agent_stage_snapshots_score_contract CHECK (
        (stage_kind = 'orchestration' AND quality_status IS NULL AND score IS NULL)
        OR (stage_kind = 'quality' AND execution_status = 'unavailable'
            AND quality_status IN ('unavailable', 'insufficient') AND score IS NULL)
        OR (stage_kind = 'quality' AND quality_status IN ('passed', 'partial', 'retry', 'insufficient')
            AND score IS NOT NULL)
        OR (stage_kind = 'quality' AND quality_status IN ('unavailable', 'skipped')
            AND score IS NULL)
    );
