CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.substations (
    manufacturer_id text NOT NULL,
    substation_id integer NOT NULL,
    configuration_type text,
    PRIMARY KEY (manufacturer_id, substation_id)
);

CREATE TABLE IF NOT EXISTS public.fault_events (
    fault_event_id text PRIMARY KEY,
    manufacturer_id text NOT NULL,
    substation_id integer NOT NULL,
    fault_label text NOT NULL,
    estimated_lead_time_hours double precision,
    lead_time_bucket text,
    FOREIGN KEY (manufacturer_id, substation_id)
        REFERENCES public.substations(manufacturer_id, substation_id)
);

CREATE TABLE IF NOT EXISTS public.sensor_readings (
    sensor_reading_id uuid PRIMARY KEY,
    manufacturer_id text NOT NULL,
    substation_id integer NOT NULL,
    reading_time timestamptz NOT NULL,
    source_sensor text NOT NULL,
    sensor_value double precision,
    unit text,
    source_file text,
    FOREIGN KEY (manufacturer_id, substation_id)
        REFERENCES public.substations(manufacturer_id, substation_id)
);

CREATE TABLE IF NOT EXISTS public.windows (
    window_id uuid PRIMARY KEY,
    manufacturer_id text NOT NULL,
    substation_id integer NOT NULL,
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL,
    source_file text,
    season_bucket text,
    label text,
    fault_event_id text,
    FOREIGN KEY (manufacturer_id, substation_id)
        REFERENCES public.substations(manufacturer_id, substation_id)
);

CREATE TABLE IF NOT EXISTS public.feature_meta_map (
    feature_name text PRIMARY KEY,
    source_sensor text NOT NULL,
    meaning text NOT NULL,
    unit text,
    calculation text
);

CREATE TABLE IF NOT EXISTS public.window_features (
    window_id uuid NOT NULL REFERENCES public.windows(window_id),
    feature_name text NOT NULL,
    feature_value double precision,
    feature_source text NOT NULL DEFAULT 'window_features',
    source_sensor text,
    source_column text,
    unit text,
    calculation text,
    display_rank integer NOT NULL DEFAULT 100,
    PRIMARY KEY (window_id, feature_name)
);

CREATE TABLE IF NOT EXISTS public.model_feature_snapshots (
    window_id uuid PRIMARY KEY REFERENCES public.windows(window_id) ON DELETE CASCADE,
    feature_set_version text NOT NULL,
    features jsonb NOT NULL,
    source_artifacts jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.model_runs (
    model_run_id uuid PRIMARY KEY,
    model_family text NOT NULL,
    model_name text NOT NULL,
    model_version text,
    run_type text,
    source_artifact text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.model_outputs (
    model_output_id uuid PRIMARY KEY,
    window_id uuid NOT NULL REFERENCES public.windows(window_id) ON DELETE CASCADE,
    model_run_id uuid NOT NULL REFERENCES public.model_runs(model_run_id) ON DELETE CASCADE,
    model_family text NOT NULL,
    score_name text,
    score_value double precision,
    label_name text,
    label_value text,
    display_rank integer NOT NULL DEFAULT 100
);

CREATE TABLE IF NOT EXISTS public.priority_decisions (
    priority_decision_id uuid PRIMARY KEY,
    window_id uuid NOT NULL REFERENCES public.windows(window_id) ON DELETE CASCADE,
    current_best_priority_score double precision,
    current_best_priority_level text,
    m1_specialist_priority_score double precision,
    m1_specialist_priority_level text,
    priority_score double precision,
    priority_level text,
    priority_source text,
    m1_priority_agreement text,
    policy_version text,
    current_best_weight double precision,
    m1_specialist_weight double precision,
    decision_basis text,
    m1_specialist_primary_state text,
    m1_specialist_fault_group text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.priority_cards (
    card_id uuid PRIMARY KEY,
    priority_decision_id uuid NOT NULL
        REFERENCES public.priority_decisions(priority_decision_id) ON DELETE CASCADE,
    operational_label text,
    primary_state text,
    review_required boolean,
    trust_level text,
    why_reason text,
    recommended_action text,
    first_crossing_time timestamptz,
    stable_crossing_time timestamptz,
    stable_crossing_lead_hours double precision,
    raw_card jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.priority_card_review_reasons (
    review_reason_id bigserial PRIMARY KEY,
    card_id uuid NOT NULL REFERENCES public.priority_cards(card_id) ON DELETE CASCADE,
    reason_code text NOT NULL,
    display_rank integer NOT NULL DEFAULT 100,
    UNIQUE (card_id, reason_code)
);

CREATE TABLE IF NOT EXISTS public.sensor_summaries (
    sensor_summary_id uuid PRIMARY KEY,
    card_id uuid NOT NULL REFERENCES public.priority_cards(card_id) ON DELETE CASCADE,
    window_id uuid NOT NULL REFERENCES public.windows(window_id) ON DELETE CASCADE,
    flow_source text NOT NULL,
    model_id text,
    model_version text,
    source_artifact text,
    selection_rule text,
    feature_name text NOT NULL,
    source_sensor text,
    source_column text,
    meaning text,
    unit text,
    calculation text,
    feature_value double precision,
    display_rank integer NOT NULL DEFAULT 100,
    summary_text text
);

CREATE TABLE IF NOT EXISTS public.llm_ops_notes (
    llm_note_id bigserial PRIMARY KEY,
    card_id uuid NOT NULL REFERENCES public.priority_cards(card_id) ON DELETE CASCADE,
    summary text NOT NULL,
    action_plan text NOT NULL,
    caution text NOT NULL,
    prompt_input jsonb NOT NULL,
    llm_output jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.rag_documents (
    document_id text PRIMARY KEY,
    title text NOT NULL,
    document_type text,
    source_path text,
    source_owner text,
    version text,
    trust_level text DEFAULT 'medium',
    is_active boolean NOT NULL DEFAULT true,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.rag_chunks (
    chunk_id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES public.rag_documents(document_id) ON DELETE CASCADE,
    chunk_text text NOT NULL,
    chunk_order integer,
    section_title text,
    rag_role text,
    language text,
    source_file text,
    curated_file text,
    page_start integer,
    page_end integer,
    download_url text,
    equipment_type text,
    fault_type text,
    risk_level text,
    output_target text,
    embedding vector(1536) NOT NULL,
    embedding_source text NOT NULL DEFAULT 'hash-v1',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rag_chunks_role_idx ON public.rag_chunks(rag_role);
CREATE INDEX IF NOT EXISTS rag_chunks_fault_idx ON public.rag_chunks(fault_type);
CREATE INDEX IF NOT EXISTS rag_chunks_equipment_idx ON public.rag_chunks(equipment_type);
CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx
    ON public.rag_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 64);

CREATE TABLE IF NOT EXISTS public.substation_building_context (
    substation_id integer PRIMARY KEY,
    apartment_name text NOT NULL,
    kapt_code text,
    life_zone text,
    dong text,
    village text,
    road_address text,
    jibun_address text,
    latitude double precision,
    longitude double precision,
    heating_type text,
    household_count integer,
    building_count integer,
    gross_floor_area_m2 double precision,
    private_usage_cost_latest_month_krw numeric,
    private_usage_cost_latest_month_unit_krw_per_m2 numeric,
    predist_configuration_type text,
    predist_configuration_ko text,
    predist_sensor_groups_ko text,
    predist_sensor_column_count integer,
    predist_has_outdoor_temperature_sensor integer,
    predist_has_space_heating_sensor integer,
    predist_has_dhw_sensor integer,
    predist_has_dhw_storage_sensor integer,
    predist_has_primary_heat_meter_sensor integer,
    predist_has_primary_supply_return_temp_sensor integer,
    mapping_note text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
