create extension if not exists vector;

create table if not exists rag_documents (
    document_id text primary key,
    title text not null,
    document_type text,
    source_path text,
    source_owner text,
    version text,
    trust_level text default 'medium',
    is_active boolean not null default true,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists rag_chunks (
    chunk_id text primary key,
    document_id text not null references rag_documents(document_id) on delete cascade,
    chunk_text text not null,
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
    embedding vector(1536) not null,
    embedding_source text not null default 'hash-v1',
    metadata jsonb not null default '{}'::jsonb,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists rag_chunks_role_idx on rag_chunks(rag_role);
create index if not exists rag_chunks_fault_idx on rag_chunks(fault_type);
create index if not exists rag_chunks_equipment_idx on rag_chunks(equipment_type);
create index if not exists rag_chunks_embedding_idx
    on rag_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 64);

create table if not exists substation_building_context (
    substation_id integer primary key,
    apartment_name text not null,
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
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists ops_agent_runs (
    run_id uuid primary key,
    card_id text,
    window_id text,
    substation_id integer,
    apartment_name text,
    window_start timestamptz,
    window_end timestamptz,
    priority text,
    suspected_type text,
    summary text,
    action_plan jsonb not null default '[]'::jsonb,
    caution jsonb not null default '[]'::jsonb,
    model_name text,
    prompt_version text,
    input_tokens integer,
    output_tokens integer,
    total_tokens integer,
    latency_ms integer,
    validation_ok boolean,
    status text not null default 'ok',
    output_json jsonb not null default '{}'::jsonb,
    external_context_json jsonb not null default '{}'::jsonb,
    validation_json jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists ops_agent_runs_created_idx on ops_agent_runs(created_at desc);
create index if not exists ops_agent_runs_substation_idx on ops_agent_runs(substation_id, created_at desc);
create index if not exists ops_agent_runs_priority_idx on ops_agent_runs(priority, created_at desc);

create table if not exists ops_retrieval_hits (
    id bigserial primary key,
    run_id uuid not null references ops_agent_runs(run_id) on delete cascade,
    chunk_id text references rag_chunks(chunk_id),
    rank integer not null,
    score double precision,
    document_type text,
    rag_role text,
    equipment_type text,
    fault_type text,
    created_at timestamptz not null default now()
);

create index if not exists ops_retrieval_hits_run_idx on ops_retrieval_hits(run_id, rank);

create table if not exists ops_tool_calls (
    id bigserial primary key,
    run_id uuid not null references ops_agent_runs(run_id) on delete cascade,
    tool_name text not null,
    tool_input jsonb not null default '{}'::jsonb,
    tool_output_summary jsonb not null default '{}'::jsonb,
    latency_ms integer,
    success boolean not null default true,
    created_at timestamptz not null default now()
);

create index if not exists ops_tool_calls_run_idx on ops_tool_calls(run_id, created_at);
