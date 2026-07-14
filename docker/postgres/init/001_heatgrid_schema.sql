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
