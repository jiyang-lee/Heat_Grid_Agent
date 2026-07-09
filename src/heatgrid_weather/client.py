from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


KMA_APIHUB_ASOS_HOURLY_RANGE_URL = "https://apihub.kma.go.kr/api/typ01/url/kma_sfctm3.php"
KMA_APIHUB_ASOS_DAILY_RANGE_URL = "https://apihub.kma.go.kr/api/typ01/url/kma_sfcdd3.php"
SEJONG_ASOS_STATION_ID = "239"


class KmaApiError(RuntimeError):
    """Raised when the KMA/data.go.kr API returns an error response."""


@dataclass(frozen=True)
class KmaAsosClient:
    service_key: str
    station_id: str = SEJONG_ASOS_STATION_ID
    timeout_seconds: int = 20

    @classmethod
    def from_env(cls, station_id: str = SEJONG_ASOS_STATION_ID) -> "KmaAsosClient":
        service_key = os.getenv("KMA_SERVICE_KEY", "").strip()
        if not service_key:
            raise KmaApiError("KMA_SERVICE_KEY environment variable is required.")
        return cls(service_key=service_key, station_id=station_id)

    def fetch_hourly(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        params = {
            "tm1": start.strftime("%Y%m%d%H%M"),
            "tm2": end.strftime("%Y%m%d%H%M"),
            "stn": self.station_id,
            "help": "0",
            "authKey": self.service_key,
        }
        url = f"{KMA_APIHUB_ASOS_HOURLY_RANGE_URL}?{urlencode(params)}"
        request = Request(url, headers={"User-Agent": "HeatGrid-Agent/0.1"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:300]
            raise KmaApiError(f"KMA API HTTP {exc.code}: {detail or exc.reason}") from exc
        except URLError as exc:
            raise KmaApiError(f"KMA API request failed: {exc.reason}") from exc

        if "활용신청이 필요한 API" in payload:
            raise KmaApiError("KMA APIHub authorization required for ASOS hourly range API.")
        if '"status"' in payload and '"message"' in payload:
            raise KmaApiError(f"KMA APIHub error: {payload[:300]}")
        return parse_apihub_asos_hourly_text(payload)

    def fetch_daily(self, start: datetime, end: datetime) -> list[dict[str, Any]]:
        params = {
            "tm1": start.strftime("%Y%m%d"),
            "tm2": end.strftime("%Y%m%d"),
            "stn": self.station_id,
            "help": "0",
            "authKey": self.service_key,
        }
        url = f"{KMA_APIHUB_ASOS_DAILY_RANGE_URL}?{urlencode(params)}"
        request = Request(url, headers={"User-Agent": "HeatGrid-Agent/0.1"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:300]
            raise KmaApiError(f"KMA API HTTP {exc.code}: {detail or exc.reason}") from exc
        except URLError as exc:
            raise KmaApiError(f"KMA API request failed: {exc.reason}") from exc

        if "활용신청이 필요한 API" in payload:
            raise KmaApiError("KMA APIHub authorization required for ASOS daily range API.")
        if '"status"' in payload and '"message"' in payload:
            raise KmaApiError(f"KMA APIHub error: {payload[:300]}")
        return parse_apihub_asos_daily_text(payload)


def parse_apihub_time(first: str, second: str | None = None) -> tuple[str, int]:
    if second and len(first) == 10 and ":" in second:
        return f"{first} {second}", 2
    if len(first) == 12 and first.isdigit():
        return f"{first[:4]}-{first[4:6]}-{first[6:8]} {first[8:10]}:{first[10:12]}", 1
    if len(first) == 10 and first.isdigit():
        return f"{first[:4]}-{first[4:6]}-{first[6:8]} {first[8:10]}:00", 1
    return first, 1


def empty_to_none(value: str) -> str | None:
    text = value.strip()
    if not text or text in {"-9", "-9.0", "-99", "-99.0"}:
        return None
    return text


def parse_apihub_asos_hourly_text(payload: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 16:
            continue
        tm, used = parse_apihub_time(parts[0], parts[1] if len(parts) > 1 else None)
        fields = parts[used:]
        if len(fields) < 16:
            continue
        rows.append(
            {
                "tm": tm,
                "stnId": empty_to_none(fields[0]),
                "stnNm": "세종" if empty_to_none(fields[0]) == SEJONG_ASOS_STATION_ID else "",
                "wd": empty_to_none(fields[1]) if len(fields) > 1 else None,
                "ws": empty_to_none(fields[2]) if len(fields) > 2 else None,
                "pa": empty_to_none(fields[6]) if len(fields) > 6 else None,
                "ps": empty_to_none(fields[7]) if len(fields) > 7 else None,
                "ta": empty_to_none(fields[10]) if len(fields) > 10 else None,
                "td": empty_to_none(fields[11]) if len(fields) > 11 else None,
                "hm": empty_to_none(fields[12]) if len(fields) > 12 else None,
                "rn": empty_to_none(fields[14]) if len(fields) > 14 else None,
                "hr3Fhsc": empty_to_none(fields[17]) if len(fields) > 17 else None,
                "dsnw": empty_to_none(fields[19]) if len(fields) > 19 else None,
            }
        )
    return rows


def parse_apihub_daily_date(value: str) -> str:
    text = value.strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text


def parse_apihub_asos_daily_text(payload: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 39:
            continue
        rows.append(
            {
                "date": parse_apihub_daily_date(parts[0]),
                "stnId": empty_to_none(parts[1]),
                "stnNm": "세종" if empty_to_none(parts[1]) == SEJONG_ASOS_STATION_ID else "",
                "wsAvg": empty_to_none(parts[2]) if len(parts) > 2 else None,
                "wsMax": empty_to_none(parts[5]) if len(parts) > 5 else None,
                "wsIns": empty_to_none(parts[8]) if len(parts) > 8 else None,
                "taAvg": empty_to_none(parts[10]) if len(parts) > 10 else None,
                "taMax": empty_to_none(parts[11]) if len(parts) > 11 else None,
                "taMin": empty_to_none(parts[13]) if len(parts) > 13 else None,
                "tdAvg": empty_to_none(parts[15]) if len(parts) > 15 else None,
                "tsAvg": empty_to_none(parts[16]) if len(parts) > 16 else None,
                "hmAvg": empty_to_none(parts[18]) if len(parts) > 18 else None,
                "hmMin": empty_to_none(parts[19]) if len(parts) > 19 else None,
                "ssDay": empty_to_none(parts[32]) if len(parts) > 32 else None,
                "rnDay": empty_to_none(parts[38]) if len(parts) > 38 else None,
                "rn60mMax": empty_to_none(parts[41]) if len(parts) > 41 else None,
                "sdNew": empty_to_none(parts[47]) if len(parts) > 47 else None,
                "sdMax": empty_to_none(parts[49]) if len(parts) > 49 else None,
            }
        )
    return rows
