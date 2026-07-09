from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Any

from .client import KmaAsosClient, SEJONG_ASOS_STATION_ID
from .context import num


def parse_date(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {value}")


def vals(rows: list[dict[str, Any]], key: str) -> list[float]:
    result = []
    for row in rows:
        value = num(row.get(key))
        if value is not None:
            result.append(value)
    return result


def avg(rows: list[dict[str, Any]], key: str) -> float | None:
    values = vals(rows, key)
    return round(mean(values), 3) if values else None


def total(rows: list[dict[str, Any]], key: str) -> float:
    return round(sum(vals(rows, key)), 3)


def min_value(rows: list[dict[str, Any]], key: str) -> float | None:
    values = vals(rows, key)
    return round(min(values), 3) if values else None


def max_value(rows: list[dict[str, Any]], key: str) -> float | None:
    values = vals(rows, key)
    return round(max(values), 3) if values else None


def heating_degree_days(rows: list[dict[str, Any]], base_temperature_c: float = 18.0) -> float:
    result = 0.0
    for value in vals(rows, "taAvg"):
        result += max(0.0, base_temperature_c - value)
    return round(result, 3)


def weather_factors(metrics: dict[str, Any]) -> list[str]:
    factors: list[str] = []
    if metrics.get("avg_temperature_c") is not None and metrics["avg_temperature_c"] <= 5:
        factors.append("기간 평균 외기온 낮음")
    if metrics.get("min_temperature_c") is not None and metrics["min_temperature_c"] <= 0:
        factors.append("영하권 일 최저기온 포함")
    if metrics.get("total_precipitation_mm") is not None and metrics["total_precipitation_mm"] >= 10:
        factors.append("기간 누적 강수 존재")
    if metrics.get("max_snow_depth_cm") is not None and metrics["max_snow_depth_cm"] > 0:
        factors.append("적설 조건 포함")
    if metrics.get("max_wind_speed_mps") is not None and metrics["max_wind_speed_mps"] >= 7:
        factors.append("강풍성 조건 포함")
    if metrics.get("heating_degree_days") is not None and metrics["heating_degree_days"] >= 50:
        factors.append("난방도일 기준 난방 부하 증가 가능")
    return factors


def build_daily_interpretation(factors: list[str]) -> str:
    if not factors:
        return "조회 기간에 월간 리포트에서 강조할 만한 뚜렷한 기상 부하 요인은 확인되지 않았습니다."
    return "조회 기간에는 " + ", ".join(factors) + " 요인이 있어 월간 운영 리포트에서 난방/급탕 부하 맥락으로 함께 설명할 수 있습니다."


def build_daily_weather_summary(
    start_date: str | datetime,
    end_date: str | datetime,
    *,
    station_id: str = SEJONG_ASOS_STATION_ID,
    client: KmaAsosClient | None = None,
) -> dict[str, Any]:
    start = parse_date(start_date)
    end = parse_date(end_date)
    if end < start:
        raise ValueError("end_date must be greater than or equal to start_date.")
    client = client or KmaAsosClient.from_env(station_id=station_id)
    rows = client.fetch_daily(start, end)

    station_name = ""
    if rows:
        station_name = str(rows[0].get("stnNm", ""))

    metrics = {
        "avg_temperature_c": avg(rows, "taAvg"),
        "min_temperature_c": min_value(rows, "taMin"),
        "max_temperature_c": max_value(rows, "taMax"),
        "total_precipitation_mm": total(rows, "rnDay"),
        "max_1h_precipitation_mm": max_value(rows, "rn60mMax"),
        "max_snow_depth_cm": max_value(rows, "sdMax"),
        "avg_humidity_pct": avg(rows, "hmAvg"),
        "avg_wind_speed_mps": avg(rows, "wsAvg"),
        "max_wind_speed_mps": max_value(rows, "wsMax"),
        "heating_degree_days": heating_degree_days(rows),
    }
    factors = weather_factors(metrics)
    return {
        "source": "KMA APIHub ASOS daily observations",
        "api_endpoint": "kma_sfcdd3.php",
        "station_id": station_id,
        "station_name": station_name,
        "region": "세종",
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "record_count": len(rows),
        "weather_factors": factors,
        "metrics": metrics,
        "interpretation": build_daily_interpretation(factors),
        "caution": "일자료 기상 요약은 월간/기간 리포트의 운영 부하 맥락 보조 근거이며 고장 원인을 단정하는 근거로 사용하지 않습니다.",
    }
