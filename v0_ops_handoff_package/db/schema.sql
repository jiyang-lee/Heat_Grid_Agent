create table if not exists substations (
    manufacturer_id text not null,
    substation_id integer not null,
    configuration_type text,
    primary key (manufacturer_id, substation_id)
);

create table if not exists fault_events (
    fault_event_id text primary key,
    manufacturer_id text not null,
    substation_id integer not null,
    fault_label text not null,
    estimated_lead_time_hours double precision,
    lead_time_bucket text,
    foreign key (manufacturer_id, substation_id)
        references substations (manufacturer_id, substation_id)
);

create table if not exists sensor_readings (
    sensor_reading_id uuid primary key,
    manufacturer_id text not null,
    substation_id integer not null,
    reading_time timestamptz not null,
    source_sensor text not null,
    sensor_value double precision,
    unit text,
    source_file text,
    foreign key (manufacturer_id, substation_id)
        references substations (manufacturer_id, substation_id)
);

create table if not exists windows (
    window_id uuid primary key,
    manufacturer_id text not null,
    substation_id integer not null,
    window_start timestamptz not null,
    window_end timestamptz not null,
    source_file text,
    season_bucket text,
    label text,
    fault_event_id text,
    foreign key (manufacturer_id, substation_id)
        references substations (manufacturer_id, substation_id)
);

alter table windows add column if not exists source_file text;
alter table windows add column if not exists season_bucket text;
alter table windows add column if not exists label text;
alter table windows add column if not exists fault_event_id text;

create table if not exists feature_meta_map (
    feature_name text primary key,
    source_sensor text not null,
    meaning text not null,
    unit text,
    calculation text
);

create table if not exists window_features (
    window_id uuid not null references windows (window_id),
    feature_name text not null,
    feature_value double precision,
    feature_source text not null default 'window_features',
    source_sensor text,
    source_column text,
    unit text,
    calculation text,
    display_rank integer not null default 100,
    primary key (window_id, feature_name)
);

alter table window_features add column if not exists feature_source text not null default 'window_features';
alter table window_features add column if not exists source_sensor text;
alter table window_features add column if not exists source_column text;
alter table window_features add column if not exists unit text;
alter table window_features add column if not exists calculation text;

create table if not exists model_runs (
    model_run_id uuid primary key,
    model_family text not null,
    model_name text not null,
    model_version text,
    run_type text not null,
    source_artifact text,
    created_at timestamptz not null default now()
);

create table if not exists model_outputs (
    model_output_id uuid primary key,
    window_id uuid not null references windows (window_id),
    model_run_id uuid not null references model_runs (model_run_id),
    model_family text not null,
    score_name text,
    score_value double precision,
    label_name text,
    label_value text,
    display_rank integer not null default 100
);

create table if not exists priority_decisions (
    priority_decision_id uuid primary key,
    window_id uuid not null references windows (window_id),
    current_best_priority_score double precision,
    current_best_priority_level text,
    m1_specialist_priority_score double precision,
    m1_specialist_priority_level text,
    priority_score double precision,
    priority_level text,
    priority_source text,
    m1_priority_agreement text,
    current_best_weight double precision,
    m1_specialist_weight double precision,
    decision_basis text,
    m1_specialist_primary_state text,
    m1_specialist_fault_group text,
    policy_version text,
    created_at timestamptz not null default now()
);

alter table priority_decisions add column if not exists current_best_weight double precision;
alter table priority_decisions add column if not exists m1_specialist_weight double precision;
alter table priority_decisions add column if not exists decision_basis text;
alter table priority_decisions add column if not exists m1_specialist_primary_state text;
alter table priority_decisions add column if not exists m1_specialist_fault_group text;

create table if not exists priority_cards (
    card_id uuid primary key,
    priority_decision_id uuid not null references priority_decisions (priority_decision_id),
    operational_label text,
    primary_state text,
    review_required boolean not null,
    trust_level text,
    first_crossing_time timestamptz,
    stable_crossing_time timestamptz,
    stable_crossing_lead_hours double precision,
    why_reason text,
    recommended_action text,
    raw_card jsonb,
    created_at timestamptz not null default now()
);

alter table priority_cards add column if not exists first_crossing_time timestamptz;
alter table priority_cards add column if not exists stable_crossing_time timestamptz;
alter table priority_cards add column if not exists stable_crossing_lead_hours double precision;
alter table priority_cards add column if not exists raw_card jsonb;

create table if not exists priority_card_review_reasons (
    review_reason_id bigserial primary key,
    card_id uuid not null references priority_cards (card_id),
    reason_code text not null,
    display_rank integer not null default 100,
    unique (card_id, reason_code)
);

create table if not exists sensor_summaries (
    sensor_summary_id uuid primary key,
    card_id uuid not null references priority_cards (card_id),
    window_id uuid not null references windows (window_id),
    flow_source text not null,
    model_id text,
    model_version text,
    source_artifact text,
    selection_rule text,
    feature_name text not null,
    source_sensor text not null,
    source_column text,
    meaning text not null,
    unit text,
    calculation text,
    feature_value double precision,
    display_rank integer not null default 100,
    summary_text text
);

create table if not exists llm_ops_notes (
    llm_note_id bigserial primary key,
    card_id uuid not null references priority_cards (card_id),
    summary text not null,
    action_plan text not null,
    caution text not null,
    prompt_input jsonb not null,
    llm_output jsonb not null,
    created_at timestamptz not null default now()
);
