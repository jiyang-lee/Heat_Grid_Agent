\echo '1) tables'
select table_name
from information_schema.tables
where table_schema = 'public'
order by table_name;

\echo '2) sensor_summaries counts'
select flow_source, count(*) as row_count
from sensor_summaries
group by flow_source
order by flow_source;

\echo '3) priority decision'
select
    priority_score,
    priority_level,
    priority_source,
    current_best_priority_score,
    m1_specialist_priority_score,
    current_best_weight,
    m1_specialist_weight
from priority_decisions
where priority_decision_id = '20000000-0000-0000-0000-000000000001';

\echo '4) first current-best raw sensor value'
select
    display_rank,
    feature_name,
    source_sensor,
    feature_value,
    unit,
    calculation
from sensor_summaries
where flow_source = 'flow1_anomaly_current_best'
order by display_rank
limit 1;

\echo '5) first M1 specialist feature'
select
    display_rank,
    feature_name,
    source_sensor,
    feature_value,
    unit,
    calculation
from sensor_summaries
where flow_source = 'flow2_m1_specialist'
order by display_rank
limit 1;