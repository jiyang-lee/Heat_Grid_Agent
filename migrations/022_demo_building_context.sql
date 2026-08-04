INSERT INTO public.substation_building_context (
    substation_id,
    substation_uid,
    apartment_name,
    mapping_note
)
SELECT
    seed.substation_id,
    substations.substation_uid,
    seed.apartment_name,
    'HeatGrid demo work-order building label'
FROM (
    VALUES
        (1, '도램마을10단지호반베르디움아파트'),
        (10, '도램마을19단지아파트'),
        (30, '범지기마을9단지한신휴플러스리버파크아파트')
) AS seed(substation_id, apartment_name)
JOIN public.substations
  ON substations.manufacturer_id = 'manufacturer 1'
 AND substations.substation_id = seed.substation_id
ON CONFLICT (substation_id) DO UPDATE
SET apartment_name = EXCLUDED.apartment_name,
    mapping_note = EXCLUDED.mapping_note,
    updated_at = now();
