# Agent Feature Contract

## What to store in DB

- selected feature columns: 195
- metadata columns: 37
- total feature rows in catalog: 259

## Rule

Preprocessing is not feature engineering. Preprocessing is cleaning, alignment, windowing, split, and leakage control. Feature engineering is the derived columns stored in `feature_columns.csv`.

## Selected feature families

- cyclic_time: 6
- derived_one_hot: 44
- event_context: 2
- sensor_numeric: 137
- time_context: 6

## Selected feature names

### cyclic_time
- `dow_cos`
- `dow_sin`
- `doy_cos`
- `doy_sin`
- `hour_cos`
- `hour_sin`

### derived_one_hot
- `configuration_type__is__missing`
- `configuration_type__is__sh`
- `configuration_type__is__sh_dhw`
- `configuration_type__is__sh_dhw_with_sub_circuits`
- `configuration_type__is__sh_with_buffer_tank`
- `configuration_type__is__sh_with_sub_circuits`
- `manufacturer__is__manufacturer_1`
- `manufacturer__is__manufacturer_2`
- `s_dhw_3-way_valve_status__dominant__is__aus`
- `s_dhw_3-way_valve_status__dominant__is__ein`
- `s_dhw_3-way_valve_status__dominant__is__missing`
- `s_dhw_control_unit_mode__dominant__is__missing`
- `s_dhw_control_unit_mode__dominant__is__standby`
- `s_dhw_control_unit_mode__dominant__is__tag`
- `s_hc1.1_control_unit_mode__dominant__is__missing`
- `s_hc1.1_control_unit_mode__dominant__is__nacht`
- `s_hc1.1_control_unit_mode__dominant__is__tag`
- `s_hc1.1_heating_pump_status__dominant__is__ein`
- `s_hc1.1_heating_pump_status__dominant__is__missing`
- `s_hc1.2_control_unit_mode__dominant__is__missing`
- `s_hc1.2_control_unit_mode__dominant__is__nacht`
- `s_hc1.2_control_unit_mode__dominant__is__standby`
- `s_hc1.2_control_unit_mode__dominant__is__tag`
- `s_hc1.2_dhw_control unit_mode__dominant__is__missing`
- `s_hc1.2_dhw_control unit_mode__dominant__is__standby`
- `s_hc1.2_heating_pump_status__dominant__is__aus`
- `s_hc1.2_heating_pump_status__dominant__is__ein`
- `s_hc1.2_heating_pump_status__dominant__is__missing`
- `s_hc1.3_control_unit_mode__dominant__is__missing`
- `s_hc1.3_control_unit_mode__dominant__is__tag`
- `s_hc1.3_heating_pump_status__dominant__is__aus`
- `s_hc1.3_heating_pump_status__dominant__is__ein`
- `s_hc1.3_heating_pump_status__dominant__is__missing`
- `s_hc1_control_unit_mode__dominant__is__missing`
- `s_hc1_control_unit_mode__dominant__is__nacht`
- `s_hc1_control_unit_mode__dominant__is__standby`
- `s_hc1_control_unit_mode__dominant__is__tag`
- `s_hc1_heating_pump_status_setpoint__dominant__is__aus`
- `s_hc1_heating_pump_status_setpoint__dominant__is__ein`
- `s_hc1_heating_pump_status_setpoint__dominant__is__missing`
- `season_bucket__is__autumn`
- `season_bucket__is__spring`
- `season_bucket__is__summer`
- `season_bucket__is__winter`

### event_context
- `days_since_last_any_event`
- `days_since_last_task_event`

### sensor_numeric
- `dhw_supply_temperature_gap__last`
- `dhw_supply_temperature_gap__max_abs`
- `dhw_supply_temperature_gap__mean`
- `extreme_change_count`
- `has_buffer_tank`
- `has_dhw`
- `hc1_supply_temperature_gap__last`
- `hc1_supply_temperature_gap__max_abs`
- `hc1_supply_temperature_gap__mean`
- `max_timestamp_gap_minutes`
- `missing_count`
- `missing_rate`
- `network_temperature_gap__last`
- `network_temperature_gap__max_abs`
- `network_temperature_gap__mean`
- `outdoor_temperature__delta`
- `outdoor_temperature__first`
- `outdoor_temperature__last`
- `outdoor_temperature__max`
- `outdoor_temperature__mean`
- `outdoor_temperature__min`
- `outdoor_temperature__std`
- `p_hc1_return_temperature__delta`
- `p_hc1_return_temperature__first`
- `p_hc1_return_temperature__last`
- `p_hc1_return_temperature__max`
- `p_hc1_return_temperature__mean`
- `p_hc1_return_temperature__min`
- `p_hc1_return_temperature__std`
- `p_net_meter_energy__delta`
- `p_net_meter_energy__first`
- `p_net_meter_energy__last`
- `p_net_meter_energy__max`
- `p_net_meter_energy__mean`
- `p_net_meter_energy__min`
- `p_net_meter_energy__missing_count`
- `p_net_meter_energy__missing_rate`
- `p_net_meter_energy__std`
- `p_net_meter_flow__delta`
- `p_net_meter_flow__first`
- `p_net_meter_flow__last`
- `p_net_meter_flow__max`
- `p_net_meter_flow__mean`
- `p_net_meter_flow__min`
- `p_net_meter_flow__missing_count`
- `p_net_meter_flow__missing_rate`
- `p_net_meter_flow__std`
- `p_net_meter_heat_power__delta`
- `p_net_meter_heat_power__first`
- `p_net_meter_heat_power__last`
- `p_net_meter_heat_power__max`
- `p_net_meter_heat_power__mean`
- `p_net_meter_heat_power__min`
- `p_net_meter_heat_power__missing_count`
- `p_net_meter_heat_power__missing_rate`
- `p_net_meter_heat_power__std`
- `p_net_meter_volume__delta`
- `p_net_meter_volume__first`
- `p_net_meter_volume__last`
- `p_net_meter_volume__max`
- `p_net_meter_volume__mean`
- `p_net_meter_volume__min`
- `p_net_meter_volume__missing_count`
- `p_net_meter_volume__missing_rate`
- `p_net_meter_volume__std`
- `p_net_return_temperature__delta`
- `p_net_return_temperature__first`
- `p_net_return_temperature__last`
- `p_net_return_temperature__max`
- `p_net_return_temperature__mean`
- `p_net_return_temperature__min`
- `p_net_return_temperature__missing_count`
- `p_net_return_temperature__missing_rate`
- `p_net_return_temperature__std`
- `p_net_supply_temperature__delta`
- `p_net_supply_temperature__first`
- `p_net_supply_temperature__last`
- `p_net_supply_temperature__max`
- `p_net_supply_temperature__mean`
- `p_net_supply_temperature__min`
- `p_net_supply_temperature__missing_count`
- `p_net_supply_temperature__missing_rate`
- `p_net_supply_temperature__std`
- `row_count`
- `s_dhw_lower_storage_temperature__delta`
- `s_dhw_lower_storage_temperature__first`
- `s_dhw_lower_storage_temperature__last`
- `s_dhw_lower_storage_temperature__max`
- `s_dhw_lower_storage_temperature__mean`
- `s_dhw_lower_storage_temperature__min`
- `s_dhw_lower_storage_temperature__missing_count`
- `s_dhw_lower_storage_temperature__missing_rate`
- `s_dhw_lower_storage_temperature__std`
- `s_dhw_supply_temperature__delta`
- `s_dhw_supply_temperature__first`
- `s_dhw_supply_temperature__last`
- `s_dhw_supply_temperature__max`
- `s_dhw_supply_temperature__mean`
- `s_dhw_supply_temperature__min`
- `s_dhw_supply_temperature__missing_count`
- `s_dhw_supply_temperature__missing_rate`
- `s_dhw_supply_temperature__std`
- `s_dhw_supply_temperature_setpoint__delta`
- `s_dhw_supply_temperature_setpoint__first`
- `s_dhw_supply_temperature_setpoint__last`
- `s_dhw_supply_temperature_setpoint__max`
- `s_dhw_supply_temperature_setpoint__mean`
- `s_dhw_supply_temperature_setpoint__min`
- `s_dhw_supply_temperature_setpoint__missing_count`
- `s_dhw_supply_temperature_setpoint__missing_rate`
- `s_dhw_supply_temperature_setpoint__std`
- `s_dhw_upper_storage_temperature__delta`
- `s_dhw_upper_storage_temperature__first`
- `s_dhw_upper_storage_temperature__last`
- `s_dhw_upper_storage_temperature__max`
- `s_dhw_upper_storage_temperature__mean`
- `s_dhw_upper_storage_temperature__min`
- `s_dhw_upper_storage_temperature__missing_count`
- `s_dhw_upper_storage_temperature__missing_rate`
- `s_dhw_upper_storage_temperature__std`
- `s_hc1_supply_temperature__delta`
- `s_hc1_supply_temperature__first`
- `s_hc1_supply_temperature__last`
- `s_hc1_supply_temperature__max`
- `s_hc1_supply_temperature__mean`
- `s_hc1_supply_temperature__min`
- `s_hc1_supply_temperature__std`
- `s_hc1_supply_temperature_setpoint__delta`
- `s_hc1_supply_temperature_setpoint__first`
- `s_hc1_supply_temperature_setpoint__last`
- `s_hc1_supply_temperature_setpoint__max`
- `s_hc1_supply_temperature_setpoint__mean`
- `s_hc1_supply_temperature_setpoint__min`
- `s_hc1_supply_temperature_setpoint__missing_count`
- `s_hc1_supply_temperature_setpoint__missing_rate`
- `s_hc1_supply_temperature_setpoint__std`
- `timestamp_gap_count`

### time_context
- `day_of_week`
- `day_of_year`
- `hour_of_day`
- `is_heating_season`
- `is_weekend`
- `month`

## Metadata columns

- `manufacturer` - identifier - `str`
- `substation_id` - identifier - `int64`
- `source_file` - source_trace - `str`
- `window_start` - time_range - `str`
- `window_end` - time_range - `str`
- `main_missing_sensors` - explanation_text - `str`
- `main_changed_sensors` - explanation_text - `str`
- `season_bucket` - time_context - `str`
- `label` - target - `str`
- `fault_label` - target_context - `str`
- `fault_event_id` - event_identifier - `float64`
- `estimated_lead_time_hours` - lead_time_target - `float64`
- `normal_event_related` - label_context - `bool`
- `maintenance_related` - interpretation_context - `bool`
- `disturbance_count` - interpretation_context - `int64`
- `leakage_blocked_fault_count` - leakage_guard - `int64`
- `window_source_type` - training_control - `str`
- `use_for_supervised_training` - training_control - `bool`
- `configuration_type` - configuration_context - `str`
- `normal_reference_group` - configuration_context - `str`
- `s_hc1_control_unit_mode__dominant` - control_context - `str`
- `s_dhw_control_unit_mode__dominant` - control_context - `str`
- `s_hc1_heating_pump_status_setpoint__dominant` - control_context - `str`
- `s_dhw_3-way_valve_status__dominant` - control_context - `str`
- `s_hc1.2_heating_pump_status__dominant` - control_context - `str`
- `s_hc1.3_heating_pump_status__dominant` - control_context - `str`
- `s_hc1.1_control_unit_mode__dominant` - control_context - `str`
- `s_hc1.2_control_unit_mode__dominant` - control_context - `str`
- `s_hc1.2_dhw_control unit_mode__dominant` - control_context - `str`
- `s_hc1.1_heating_pump_status__dominant` - control_context - `str`
- `s_hc1.3_control_unit_mode__dominant` - control_context - `str`
- `split_time_based` - evaluation_split - `str`
- `split_substation_based` - evaluation_split - `str`
- `split_regime_based` - evaluation_split - `str`
- `normal_reference_outlier` - training_control - `bool`
- `normal_reference_outlier_count` - training_control - `int64`
- `normal_reference_filter_reason` - training_control - `str`

## DB recommendation

- store `selected_feature_columns` as the agent-callable feature schema
- store `metadata_columns` separately as non-feature context/labels
- use `column_name` as the primary key
- keep `feature_family` for filtering and model contract versioning