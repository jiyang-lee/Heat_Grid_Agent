from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

from .client import KmaAsosClient, SEJONG_ASOS_STATION_ID


def parse_weather_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def parse_agent_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value.replace(minute=0, second=0, microsecond=0)
    text = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d%H", "%Y%m%d %H"):
        try:
            return datetime.strptime(text, fmt).replace(minute=0, second=0, microsecond=0)
        except ValueError:
            continue
    raise ValueError(f"Unsupported datetime format: {value}")


def num(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def values(rows: list[dict[str, Any]], key: str) -> list[float]:
    result: list[float] = []
    for row in rows:
        value = num(row.get(key))
        if value is not None:
            result.append(value)
    return result


def avg(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = values(rows, key)
    return round(mean(vals), 3) if vals else None


def total(rows: list[dict[str, Any]], key: str) -> float:
    return round(sum(values(rows, key)), 3)


def max_value(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = values(rows, key)
    return round(max(vals), 3) if vals else None


def min_value(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = values(rows, key)
    return round(min(vals), 3) if vals else None


def filter_window(rows: list[dict[str, Any]], start: datetime, end: datetime) -> list[dict[str, Any]]:
    selected = []
    for row in rows:
        tm = row.get("tm")
        if not tm:
            continue
        observed_at = parse_weather_time(str(tm))
        if start <= observed_at <= end:
            selected.append(row)
    return selected


def heating_degree_hours(rows: list[dict[str, Any]], base_temperature_c: float = 18.0) -> float:
    total_value = 0.0
    for temperature in values(rows, "ta"):
        total_value += max(0.0, base_temperature_c - temperature)
    return round(total_value, 3)


@dataclass(frozen=True)
class WeatherRelevance:
    score: int
    factors: list[str]

    @property
    def level(self) -> str:
        if self.score >= 5:
            return "high"
        if self.score >= 3:
            return "medium"
        if self.score >= 1:
            return "low"
        return "none"


def judge_relevance(metrics: dict[str, Any]) -> WeatherRelevance:
    score = 0
    factors: list[str] = []

    avg_temp = metrics.get("avg_temperature_c")
    min_temp = metrics.get("min_temperature_c")
    temp_delta = metrics.get("temperature_delta_24h_c")
    precipitation = metrics.get("precipitation_mm")
    snow_depth = metrics.get("snow_depth_cm")
    max_wind = metrics.get("max_wind_speed_mps")
    hdh = metrics.get("heating_degree_hours")

    if avg_temp is not None and avg_temp <= 5:
        score += 2
        factors.append("외기온 낮음")
    if min_temp is not None and min_temp <= 0:
        score += 1
        factors.append("영하권 시간대 포함")
    if temp_delta is not None and temp_delta <= -5:
        score += 2
        factors.append("전일 동시간대 대비 기온 급락")
    elif temp_delta is not None and temp_delta <= -3:
        score += 1
        factors.append("전일 동시간대 대비 기온 하락")
    if precipitation is not None and precipitation >= 1:
        score += 1
        factors.append("강수 발생")
    if snow_depth is not None and snow_depth > 0:
        score += 2
        factors.append("적설 또는 눈 관련 조건")
    if max_wind is not None and max_wind >= 7:
        score += 1
        factors.append("강한 바람")
    if hdh is not None and hdh >= 60:
        score += 1
        factors.append("난방도시 기준 난방 부하 증가 가능")

    return WeatherRelevance(score=score, factors=factors)


def build_interpretation(relevance: WeatherRelevance) -> str:
    if relevance.level == "none":
        return "조회 구간에서 이상 신호 해석을 보완할 만한 뚜렷한 기상 요인은 확인되지 않았습니다."
    if relevance.level == "low":
        return "일부 기상 요인이 있으나 이상 신호를 설명할 정도의 강한 운영 부하 맥락은 제한적입니다."
    if relevance.level == "medium":
        return "외기 조건상 난방 또는 급탕 부하가 증가했을 가능성이 있어 이상 신호 해석 시 운영 맥락으로 함께 확인할 필요가 있습니다."
    return "기상 조건이 뚜렷하게 불리해 난방 부하 증가 가능성이 큽니다. 다만 이는 고장 원인 확정이 아니라 위험도 판단을 보완하는 운영 맥락입니다."


def build_weather_context(
    window_start: str | datetime,
    window_end: str | datetime,
    *,
    station_id: str = SEJONG_ASOS_STATION_ID,
    client: KmaAsosClient | None = None,
) -> dict[str, Any]:
    start = parse_agent_time(window_start)
    end = parse_agent_time(window_end)
    if end < start:
        raise ValueError("window_end must be greater than or equal to window_start.")

    fetch_start = start - timedelta(hours=24)
    client = client or KmaAsosClient.from_env(station_id=station_id)
    all_rows = client.fetch_hourly(fetch_start, end)

    current_rows = filter_window(all_rows, start, end)
    previous_rows = filter_window(all_rows, start - timedelta(hours=24), end - timedelta(hours=24))

    current_avg_temp = avg(current_rows, "ta")
    previous_avg_temp = avg(previous_rows, "ta")
    temperature_delta = None
    if current_avg_temp is not None and previous_avg_temp is not None:
        temperature_delta = round(current_avg_temp - previous_avg_temp, 3)

    station_name = ""
    if current_rows:
        station_name = str(current_rows[0].get("stnNm", ""))
    elif all_rows:
        station_name = str(all_rows[0].get("stnNm", ""))

    metrics = {
        "avg_temperature_c": current_avg_temp,
        "min_temperature_c": min_value(current_rows, "ta"),
        "max_temperature_c": max_value(current_rows, "ta"),
        "temperature_delta_24h_c": temperature_delta,
        "precipitation_mm": total(current_rows, "rn"),
        "snow_depth_cm": max_value(current_rows, "dsnw"),
        "new_snow_3h_cm": max_value(current_rows, "hr3Fhsc"),
        "avg_humidity_pct": avg(current_rows, "hm"),
        "max_wind_speed_mps": max_value(current_rows, "ws"),
        "heating_degree_hours": heating_degree_hours(current_rows),
    }
    relevance = judge_relevance(metrics)
    return {
        "source": "KMA APIHub ASOS hourly observations",
        "api_endpoint": "kma_sfctm3.php",
        "station_id": station_id,
        "station_name": station_name,
        "region": "세종",
        "window_start": start.strftime("%Y-%m-%d %H:%M:%S"),
        "window_end": end.strftime("%Y-%m-%d %H:%M:%S"),
        "record_count": len(current_rows),
        "comparison_record_count_24h": len(previous_rows),
        "is_relevant": relevance.level in {"medium", "high"},
        "relevance_level": relevance.level,
        "relevance_score": relevance.score,
        "weather_factors": relevance.factors,
        "metrics": metrics,
        "interpretation": build_interpretation(relevance),
        "caution": "기상 요인은 운영 부하 맥락 보조 근거이며 고장 원인을 단정하는 근거로 사용하지 않습니다.",
    }
