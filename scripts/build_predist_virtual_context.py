from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

CONTEXT_CSV = DATA / "external" / "substation_buildings_sejong_lifezone1_31_district_heating_context.csv"
COLUMN_DICT_CSV = DATA / "external" / "substation_buildings_sejong_lifezone1_31_district_heating_column_dictionary.csv"
RAW_INVENTORY_CSV = DATA / "interim" / "raw_inventory.csv"
RAW_SCHEMA_CSV = DATA / "interim" / "raw_schema_summary.csv"
TRAINABLE_WINDOWS_CSV = DATA / "processed" / "trainable_windows.csv"

SOURCE_CONFIGURATION_TYPES_CSV = (
    ROOT.parent
    / "HeatGrid_Agent"
    / "best"
    / "data"
    / "raw_data"
    / "predist_v2"
    / "manufacturer 1"
    / "configuration_types.csv"
)
PACKAGED_CONFIGURATION_TYPES_CSV = DATA / "external" / "source" / "predist_configuration_types_m1.csv"

PREDIST_METADATA_CSV = DATA / "external" / "predist_virtual_substation_sensor_metadata_m1.csv"
CONTEXT_WITH_PREDIST_CSV = (
    DATA / "external" / "substation_buildings_sejong_lifezone1_31_district_heating_context_with_predist.csv"
)
COLUMN_DICT_WITH_PREDIST_CSV = (
    DATA
    / "external"
    / "substation_buildings_sejong_lifezone1_31_district_heating_with_predist_column_dictionary.csv"
)


def read_csv(path: Path, delimiter: str = ",") -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=delimiter))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def clean(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def parse_int(value: object) -> int:
    text = clean(value)
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def first_value(rows: list[dict[str, str]], column: str) -> str:
    for row in rows:
        value = clean(row.get(column))
        if value:
            return value
    return ""


def normalize_configuration_type(value: str) -> str:
    aliases = {
        "SH": "난방",
        "SH + DHW": "난방 + 급탕",
        "SH with buffer tank": "난방 + 버퍼탱크",
        "SH with sub circuits": "난방 + 보조회로",
        "SH with sub-circuits": "난방 + 보조회로",
        "SH + DHW with sub circuits": "난방 + 급탕 + 보조회로",
        "SH + DHW with sub-circuits": "난방 + 급탕 + 보조회로",
    }
    return aliases.get(value, value)


def read_configuration_types() -> dict[str, str]:
    source = SOURCE_CONFIGURATION_TYPES_CSV if SOURCE_CONFIGURATION_TYPES_CSV.exists() else PACKAGED_CONFIGURATION_TYPES_CSV
    if not source.exists():
        # Fallback: trainable_windows already contains configuration_type after raw metadata import.
        config_by_sid: dict[str, str] = {}
        for row in read_csv(TRAINABLE_WINDOWS_CSV):
            sid = clean(row.get("substation_id"))
            config_type = clean(row.get("configuration_type"))
            if sid and config_type and sid not in config_by_sid:
                config_by_sid[sid] = config_type
        return config_by_sid

    rows = read_csv(source, delimiter=";")
    packaged_rows = [
        {
            "substation_id": clean(row.get("substation ID")),
            "configuration_type": clean(row.get("configuration_type")),
        }
        for row in rows
        if clean(row.get("substation ID"))
    ]
    write_csv(PACKAGED_CONFIGURATION_TYPES_CSV, packaged_rows, ["substation_id", "configuration_type"])
    return {row["substation_id"]: row["configuration_type"] for row in packaged_rows}


def summarize_raw_inventory() -> dict[str, dict[str, object]]:
    summaries: dict[str, dict[str, object]] = {}
    for row in read_csv(RAW_INVENTORY_CSV):
        if clean(row.get("manufacturer")) != "manufacturer 1":
            continue
        if clean(row.get("file_type")) != "operational_data":
            continue
        sid = clean(row.get("substation_id"))
        if not sid:
            continue
        summaries[sid] = {
            "predist_manufacturer": clean(row.get("manufacturer")),
            "predist_source_file": Path(clean(row.get("path"))).name,
            "predist_raw_file_path": clean(row.get("path")),
            "predist_raw_sampled_rows": clean(row.get("row_count_sampled")),
            "predist_raw_sampled_columns": clean(row.get("column_count_sampled")),
        }
    return summaries


def summarize_raw_schema() -> dict[str, dict[str, object]]:
    counts_by_sid: dict[str, dict[str, int]] = {}
    for row in read_csv(RAW_SCHEMA_CSV):
        if clean(row.get("manufacturer")) != "manufacturer 1":
            continue
        sid = clean(row.get("substation_id"))
        column = clean(row.get("column_name"))
        if not sid or not column:
            continue
        counts_by_sid.setdefault(sid, {})[column] = parse_int(row.get("sample_non_null_count"))

    summaries: dict[str, dict[str, object]] = {}
    for sid, counts in counts_by_sid.items():
        present_columns = {
            column for column, count in counts.items() if column != "timestamp" and count > 0
        }

        has_outdoor = "outdoor_temperature" in present_columns
        has_space_heating = any(
            column in present_columns
            for column in [
                "s_hc1_supply_temperature",
                "s_hc1_supply_temperature_setpoint",
                "p_hc1_return_temperature",
            ]
        )
        has_dhw = any(
            column in present_columns
            for column in [
                "s_dhw_supply_temperature",
                "s_dhw_supply_temperature_setpoint",
            ]
        )
        has_dhw_storage = any(
            column in present_columns
            for column in [
                "s_dhw_upper_storage_temperature",
                "s_dhw_lower_storage_temperature",
            ]
        )
        has_heat_meter = any(
            column in present_columns
            for column in [
                "p_net_meter_energy",
                "p_net_meter_volume",
                "p_net_meter_heat_power",
                "p_net_meter_flow",
            ]
        )
        has_primary_supply_return = (
            "p_net_supply_temperature" in present_columns
            and "p_net_return_temperature" in present_columns
        )

        groups: list[str] = []
        groups_ko: list[str] = []
        if has_outdoor:
            groups.append("outdoor_weather")
            groups_ko.append("외기온")
        if has_space_heating:
            groups.append("space_heating_loop")
            groups_ko.append("난방 회로")
        if has_dhw:
            groups.append("domestic_hot_water")
            groups_ko.append("급탕")
        if has_dhw_storage:
            groups.append("domestic_hot_water_storage")
            groups_ko.append("급탕 저장탱크")
        if has_heat_meter:
            groups.append("primary_heat_meter")
            groups_ko.append("1차측 열량계")
        if has_primary_supply_return:
            groups.append("primary_supply_return_temperature")
            groups_ko.append("1차측 공급/환수온도")

        summaries[sid] = {
            "predist_sensor_column_count": len(present_columns),
            "predist_sensor_groups": "|".join(groups),
            "predist_sensor_groups_ko": "|".join(groups_ko),
            "predist_has_outdoor_temperature_sensor": int(has_outdoor),
            "predist_has_space_heating_sensor": int(has_space_heating),
            "predist_has_dhw_sensor": int(has_dhw),
            "predist_has_dhw_storage_sensor": int(has_dhw_storage),
            "predist_has_primary_heat_meter_sensor": int(has_heat_meter),
            "predist_has_primary_supply_return_temp_sensor": int(has_primary_supply_return),
        }
    return summaries


PREDIST_COLUMNS = [
    "predist_mapping_type",
    "predist_mapping_note",
    "predist_manufacturer",
    "predist_source_file",
    "predist_raw_file_path",
    "predist_configuration_type",
    "predist_configuration_ko",
    "predist_sensor_groups",
    "predist_sensor_groups_ko",
    "predist_sensor_column_count",
    "predist_raw_sampled_rows",
    "predist_raw_sampled_columns",
    "predist_has_outdoor_temperature_sensor",
    "predist_has_space_heating_sensor",
    "predist_has_dhw_sensor",
    "predist_has_dhw_storage_sensor",
    "predist_has_primary_heat_meter_sensor",
    "predist_has_primary_supply_return_temp_sensor",
]


PREDIST_COLUMN_DICTIONARY = [
    {
        "column": "predist_mapping_type",
        "ko_name": "PreDist 매핑 방식",
        "description": "세종 아파트 행과 PreDist substation_id를 어떤 방식으로 연결했는지 나타냅니다.",
        "usage_note": "현재는 실제 물리 연결이 아닌 substation_id 기준 가상 매핑입니다.",
    },
    {
        "column": "predist_mapping_note",
        "ko_name": "PreDist 매핑 주석",
        "description": "가상 매핑의 한계를 명시한 설명입니다.",
        "usage_note": "프론트/Agent가 실제 현장 매칭으로 표현하지 않도록 주의 문구로 사용합니다.",
    },
    {
        "column": "predist_manufacturer",
        "ko_name": "PreDist 제조사 그룹",
        "description": "원본 PreDist 데이터의 제조사 그룹입니다.",
        "usage_note": "현재 모델 스코프는 manufacturer 1 기준입니다.",
    },
    {
        "column": "predist_source_file",
        "ko_name": "PreDist 원본 파일명",
        "description": "가상 매핑된 PreDist 운영 데이터 파일명입니다.",
        "usage_note": "간단한 출처 표시나 내부 추적용으로 사용합니다.",
    },
    {
        "column": "predist_raw_file_path",
        "ko_name": "PreDist 원본 파일 경로",
        "description": "원본 운영 데이터 CSV의 상대 경로입니다.",
        "usage_note": "DB 적재 후 원천 추적용이며 프론트 표시용은 아닙니다.",
    },
    {
        "column": "predist_configuration_type",
        "ko_name": "PreDist 설비 구성 유형",
        "description": "configuration_types.csv에서 가져온 난방/급탕 설비 구성 유형입니다.",
        "usage_note": "예: SH + DHW는 난방 + 급탕 설비를 뜻합니다.",
    },
    {
        "column": "predist_configuration_ko",
        "ko_name": "PreDist 설비 구성 한글명",
        "description": "configuration_type을 화면/설명에 쓰기 쉽게 풀어쓴 값입니다.",
        "usage_note": "프론트 카드나 Agent 설명에 사용할 수 있습니다.",
    },
    {
        "column": "predist_sensor_groups",
        "ko_name": "PreDist 센서 그룹",
        "description": "원본 샘플에서 값이 확인된 센서 묶음의 영문 코드입니다.",
        "usage_note": "DB/API에서는 이 값을 필터 조건으로 쓰기 좋습니다.",
    },
    {
        "column": "predist_sensor_groups_ko",
        "ko_name": "PreDist 센서 그룹 한글명",
        "description": "원본 샘플에서 값이 확인된 센서 묶음의 한글명입니다.",
        "usage_note": "프론트 표시와 Agent 요약 설명에 사용합니다.",
    },
    {
        "column": "predist_sensor_column_count",
        "ko_name": "사용 가능한 센서 컬럼 수",
        "description": "샘플에서 결측이 아닌 값을 가진 센서 컬럼 수입니다.",
        "usage_note": "센서 구성이 얼마나 풍부한지 보는 간단한 지표입니다.",
    },
    {
        "column": "predist_raw_sampled_rows",
        "ko_name": "원본 샘플 row 수",
        "description": "raw_inventory 생성 시 샘플링한 row 수입니다.",
        "usage_note": "원본 파일 존재와 샘플 확인용입니다.",
    },
    {
        "column": "predist_raw_sampled_columns",
        "ko_name": "원본 샘플 컬럼 수",
        "description": "raw_inventory 생성 시 확인한 원본 컬럼 수입니다.",
        "usage_note": "설비별 원본 컬럼 규모 비교에 사용합니다.",
    },
    {
        "column": "predist_has_outdoor_temperature_sensor",
        "ko_name": "외기온 센서 여부",
        "description": "outdoor_temperature 값이 원본 샘플에 존재하는지 여부입니다.",
        "usage_note": "외부 날씨 데이터와 비교할 수 있는지 판단합니다.",
    },
    {
        "column": "predist_has_space_heating_sensor",
        "ko_name": "난방 회로 센서 여부",
        "description": "난방 공급온도/설정온도/환수온도 계열 센서가 존재하는지 여부입니다.",
        "usage_note": "난방 회로 상태 판단 가능성 확인에 사용합니다.",
    },
    {
        "column": "predist_has_dhw_sensor",
        "ko_name": "급탕 센서 여부",
        "description": "급탕 공급온도/설정온도 계열 센서가 존재하는지 여부입니다.",
        "usage_note": "급탕 관련 상태 판단 가능성 확인에 사용합니다.",
    },
    {
        "column": "predist_has_dhw_storage_sensor",
        "ko_name": "급탕 저장탱크 센서 여부",
        "description": "급탕 상부/하부 저장탱크 온도 센서가 존재하는지 여부입니다.",
        "usage_note": "급탕 저장탱크 상태 판단 가능성 확인에 사용합니다.",
    },
    {
        "column": "predist_has_primary_heat_meter_sensor",
        "ko_name": "1차측 열량계 센서 여부",
        "description": "1차측 에너지/체적/열출력/유량 계열 센서가 존재하는지 여부입니다.",
        "usage_note": "열부하와 유량 기반 판단 가능성 확인에 사용합니다.",
    },
    {
        "column": "predist_has_primary_supply_return_temp_sensor",
        "ko_name": "1차측 공급/환수온도 센서 여부",
        "description": "1차측 공급온도와 환수온도 센서가 모두 존재하는지 여부입니다.",
        "usage_note": "공급-환수 온도차 기반 판단 가능성 확인에 사용합니다.",
    },
]


def build() -> None:
    context_rows = read_csv(CONTEXT_CSV)
    base_dictionary_rows = read_csv(COLUMN_DICT_CSV)

    configuration_types = read_configuration_types()
    inventory_summaries = summarize_raw_inventory()
    schema_summaries = summarize_raw_schema()

    metadata_rows: list[dict[str, object]] = []
    merged_rows: list[dict[str, object]] = []

    for row in context_rows:
        sid = clean(row.get("substation_id"))
        config_type = configuration_types.get(sid, "")
        metadata = {column: "" for column in PREDIST_COLUMNS}
        metadata["predist_mapping_type"] = "virtual_by_substation_id"
        metadata["predist_mapping_note"] = (
            "가상 매핑: 세종 아파트와 PreDist 설비의 실제 물리 연결은 검증되지 않음."
        )
        metadata.update(inventory_summaries.get(sid, {}))
        metadata.update(schema_summaries.get(sid, {}))
        metadata["predist_configuration_type"] = config_type
        metadata["predist_configuration_ko"] = normalize_configuration_type(config_type)

        metadata_rows.append({"substation_id": sid, **metadata})
        merged_rows.append({**row, **metadata})

    base_fields = list(context_rows[0].keys())
    write_csv(PREDIST_METADATA_CSV, metadata_rows, ["substation_id", *PREDIST_COLUMNS])
    write_csv(CONTEXT_WITH_PREDIST_CSV, merged_rows, [*base_fields, *PREDIST_COLUMNS])
    write_csv(
        COLUMN_DICT_WITH_PREDIST_CSV,
        [*base_dictionary_rows, *PREDIST_COLUMN_DICTIONARY],
        ["column", "ko_name", "description", "usage_note"],
    )

    print(f"wrote {PACKAGED_CONFIGURATION_TYPES_CSV}")
    print(f"wrote {PREDIST_METADATA_CSV}")
    print(f"wrote {CONTEXT_WITH_PREDIST_CSV}")
    print(f"wrote {COLUMN_DICT_WITH_PREDIST_CSV}")
    print(f"rows: {len(merged_rows)}")
    print(f"columns: {len(base_fields) + len(PREDIST_COLUMNS)}")
    print(f"sample predist fields: {', '.join(PREDIST_COLUMNS)}")


if __name__ == "__main__":
    build()
