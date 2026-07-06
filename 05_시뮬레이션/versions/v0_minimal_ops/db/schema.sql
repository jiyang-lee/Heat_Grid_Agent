create table if not exists substations (
    manufacturer_id text not null,
    substation_id integer not null,
    configuration_type text,
    primary key (manufacturer_id, substation_id)
);

create table if not exists windows (
    window_id uuid primary key,
    manufacturer_id text not null,
    substation_id integer not null,
    window_start timestamptz not null,
    window_end timestamptz not null,
    foreign key (manufacturer_id, substation_id)
        references substations (manufacturer_id, substation_id)
);

create table if not exists window_features (
    window_id uuid not null references windows (window_id),
    feature_name text not null,
    feature_value double precision,
    display_rank integer not null default 100,
    primary key (window_id, feature_name)
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
    policy_version text,
    created_at timestamptz not null default now()
);

create table if not exists priority_cards (
    card_id uuid primary key,
    priority_decision_id uuid not null references priority_decisions (priority_decision_id),
    operational_label text,
    primary_state text,
    review_required boolean not null,
    trust_level text,
    why_reason text,
    recommended_action text,
    created_at timestamptz not null default now()
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
