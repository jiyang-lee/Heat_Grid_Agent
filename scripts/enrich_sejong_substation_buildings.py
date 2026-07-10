from __future__ import annotations

import csv
import html
import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = ROOT / "data" / "external" / "substation_buildings_sejong_lifezone1_31_geocoded.csv"
OUTPUT_CSV = ROOT / "data" / "external" / "substation_buildings_sejong_lifezone1_31_enriched.csv"
MATCH_CSV = ROOT / "data" / "external" / "kapt_match_results_sejong_lifezone1_31.csv"
META_JSON = ROOT / "data" / "external" / "substation_buildings_sejong_lifezone1_31_enrichment_sources.json"
RAW_DIR = ROOT / "data" / "external" / "source" / "kapt_pages"

BASE_URL = "https://www.k-apt.go.kr"
SEARCH_DATE = "202604"
REQUEST_SLEEP_SEC = 0.15


def clean_text(value: str | None) -> str:
    if value is None or value == "":
        return ""
    value = str(value)
    value = re.sub(r"(?is)<script.*?</script>", " ", value)
    value = re.sub(r"(?is)<style.*?</style>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize(value: str | None) -> str:
    value = clean_text(value)
    value = value.lower()
    value = value.replace("아파트", "")
    return re.sub(r"[^0-9a-z가-힣]", "", value)


def parse_number(value: str | None) -> float | None:
    text = clean_text(value)
    if not text or text in {"-", "null", "None"}:
        return None
    text = text.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?(?:e[+-]?\d+)?", text, re.I)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def as_int_text(value: str | None) -> str:
    num = parse_number(value)
    if num is None:
        return ""
    return str(int(num))


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"could not decode {path}")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in fieldnames})


def clear_generated_raw_pages() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for pattern in ("[0-9][0-9]_*_basic.html", "[0-9][0-9]_*_fee.html", "[0-9][0-9]_*_main_board.json"):
        for path in RAW_DIR.glob(pattern):
            path.unlink()


def unique_nonempty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = clean_text(value)
        if not value:
            continue
        key = value
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def keyword_candidates(row: dict[str, str]) -> list[str]:
    values = []
    source_values = [
        row.get("matched_name", ""),
        row.get("original_building_name", ""),
        row.get("building_name", ""),
    ]
    for value in source_values:
        match = re.search(r"([가-힣]+마을)\s*(\d+)\s*단지", value)
        if match:
            values.append(f"{match.group(1)}{match.group(2)}단지")
            values.append(f"{match.group(1)} {match.group(2)}단지")
        no_paren = re.sub(r"\([^)]*\)", "", value)
        values.append(re.sub(r"아파트$", "", no_paren).strip())
        values.append(no_paren)
        values.append(value)
    if row.get("village"):
        values.append(row["village"])
    for value in list(values):
        match = re.search(r"([가-힣]+마을)\s*(\d+)\s*단지", value)
        if match:
            values.append(f"{match.group(1)}{match.group(2)}단지")
            values.append(f"{match.group(1)} {match.group(2)}단지")
    return unique_nonempty(values)


def extract_village_unit(row: dict[str, str]) -> tuple[str, int | None]:
    for value in (row.get("matched_name", ""), row.get("original_building_name", ""), row.get("building_name", "")):
        match = re.search(r"([가-힣]+마을)\s*(\d+)\s*단지", value)
        if match:
            return match.group(1), int(match.group(2))
    return row.get("village", ""), None


def candidate_covers_unit(candidate_name: str, village: str, unit: int | None) -> bool:
    if not village or unit is None:
        return False
    name = normalize(candidate_name)
    village_norm = normalize(village)
    if village_norm not in name:
        return False
    if re.search(rf"{unit}\s*단지", candidate_name):
        return True
    compact = re.sub(r"\s+", "", candidate_name)
    if f"{unit}단지" in compact:
        return True
    for start, end in re.findall(r"(\d+)\s*(?:~|～|-|\.|·)\s*(\d+)\s*단지", candidate_name):
        lo, hi = int(start), int(end)
        if lo <= unit <= hi:
            return True
    return False


def extract_csrf(text: str) -> str:
    patterns = [
        r'name="_csrf"\s+value="([^"]+)"',
        r'id="_csrf"\s+name="_csrf"\s+content="([^"]+)"',
        r'name="_csrf"\s+content="([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def value_after_label(page: str, label: str) -> str:
    idx = page.find(label)
    if idx < 0:
        return ""
    after = page[idx:]
    td_start = re.search(r"<td\b[^>]*>", after, re.I)
    if not td_start:
        return ""
    content_start = td_start.end()
    rest = after[content_start:]
    td_end = re.search(r"</td\s*>", rest, re.I)
    th_next = re.search(r"<th\b", rest, re.I)
    end = len(rest)
    if td_end and th_next:
        end = min(td_end.start(), th_next.start())
    elif td_end:
        end = td_end.start()
    elif th_next:
        end = th_next.start()
    return clean_text(rest[:end])


def parse_addresses_from_basic(page: str) -> tuple[str, str]:
    pairs = re.findall(
        r'arrGbn\.push\("([^"]*)"\);\s*arrAddr\.push\("([^"]*)"\);',
        page,
        flags=re.S,
    )
    legal = [addr for gbn, addr in pairs if gbn == "B" and addr and addr != "undefined"]
    road = [addr for gbn, addr in pairs if gbn == "R" and addr and addr != "undefined"]
    return "<br/>".join(legal), "<br/>".join(road)


def parse_basic_page(page: str) -> dict[str, Any]:
    legal_addr, road_addr = parse_addresses_from_basic(page)
    name_code = value_after_label(page, "명칭(단지코드)")
    match = re.match(r"(.+?)\s*\((A[0-9]+)\)", name_code)
    parsed_name = match.group(1).strip() if match else name_code
    parsed_code = match.group(2).strip() if match else ""

    building_count = ""
    household_count = ""
    building_household = value_after_label(page, "동수 / 세대수")
    match = re.search(r"(\d+)\s*/\s*(\d+)", building_household)
    if match:
        building_count = match.group(1)
        household_count = match.group(2)

    exclusive_area_band_counts = {}
    for band, count in re.findall(r"<li><b>([^<:]+)\s*:\s*</b><span>\s*([0-9,]+)\s*세대", page):
        exclusive_area_band_counts[clean_text(band)] = count.replace(",", "")

    return {
        "kapt_name": parsed_name,
        "kapt_code_from_basic": parsed_code,
        "kapt_complex_type": value_after_label(page, "단지분류"),
        "kapt_legal_address": clean_text(legal_addr),
        "kapt_road_address": clean_text(road_addr),
        "sale_type": value_after_label(page, "분양형태"),
        "management_type": value_after_label(page, "관리방식"),
        "heating_type": value_after_label(page, "난방방식"),
        "corridor_type": value_after_label(page, "복도유형"),
        "gross_floor_area_m2": as_int_text(value_after_label(page, "연면적")),
        "approval_date": value_after_label(page, "사용승인일"),
        "building_count": building_count,
        "household_count": household_count,
        "exclusive_residential_area_m2": value_after_label(page, "주거전용면적").replace("㎡", "").strip(),
        "kapt_join_date": value_after_label(page, "K-apt 가입일"),
        "exclusive_area_households_json": json.dumps(exclusive_area_band_counts, ensure_ascii=False),
        "builder_developer": value_after_label(page, "시공사 / 시행사"),
    }


def extract_json_arrays_from_page(page: str) -> list[Any]:
    arrays: list[Any] = []
    marker = "JSON.stringify("
    idx = 0
    while True:
        start = page.find(marker, idx)
        if start < 0:
            break
        pos = start + len(marker)
        while pos < len(page) and page[pos].isspace():
            pos += 1
        if pos >= len(page) or page[pos] != "[":
            idx = pos + 1
            continue
        end = find_balanced_json(page, pos)
        if end <= pos:
            idx = pos + 1
            continue
        raw = page[pos:end]
        try:
            arrays.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
        idx = end
    return arrays


def find_balanced_json(text: str, start: int) -> int:
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def parse_fee_page(page: str, household_count: str) -> dict[str, Any]:
    arrays = extract_json_arrays_from_page(page)
    relevant_codes = [
        "PRIVATE_HEAT_COST",
        "P_HEAT",
        "HEAT",
        "PRIVATE_WATER_HOT_COST",
        "P_WATER_HOT",
        "WATER_HOT",
        "PRIVATE_GAS_COST",
        "PRIVATE_ELECT_COST",
        "PRIVATE_WATER_COOL_COST",
        "PUBLIC_TOT",
        "PRIVATE_TOT",
        "S_LEVY",
        "COST_TOT",
    ]
    mapping = {
        "PUBLIC_TOT": "public_mgmt_cost",
        "PRIVATE_TOT": "private_usage_cost",
        "PRIVATE_HEAT_COST": "heat_cost",
        "P_HEAT": "heat_public_cost",
        "HEAT": "heat_private_cost",
        "PRIVATE_WATER_HOT_COST": "hot_water_cost",
        "P_WATER_HOT": "hot_water_public_cost",
        "WATER_HOT": "hot_water_private_cost",
        "PRIVATE_GAS_COST": "gas_cost",
        "PRIVATE_ELECT_COST": "electricity_cost",
        "PRIVATE_WATER_COOL_COST": "water_cost",
        "S_LEVY": "long_term_repair_reserve",
        "COST_TOT": "total_mgmt_cost",
    }

    blocks: list[tuple[list[Any], list[dict[str, Any]]]] = []
    for arr in arrays:
        if not isinstance(arr, list):
            continue
        title = next((item.get("excelTitle") for item in arr if isinstance(item, dict) and item.get("excelTitle")), [])
        result_list = next(
            (item.get("resultList") for item in arr if isinstance(item, dict) and item.get("resultList")),
            None,
        )
        if not isinstance(result_list, list):
            continue
        codes = [
            item.get("columnNm1")
            for item in result_list
            if isinstance(item, dict) and item.get("columnNm1") in relevant_codes
        ]
        if codes:
            blocks.append((title if isinstance(title, list) else [title], result_list))

    annual_block: tuple[list[Any], list[dict[str, Any]]] | None = None
    single_month_block: tuple[list[Any], list[dict[str, Any]]] | None = None
    for title, result_list in blocks:
        has_annual_keys = any(isinstance(item, dict) and "mon13" in item for item in result_list)
        has_single_month_keys = any(isinstance(item, dict) and "v0" in item for item in result_list)
        if has_annual_keys and annual_block is None:
            annual_block = (title, result_list)
        if has_single_month_keys and single_month_block is None:
            single_month_block = (title, result_list)

    if annual_block is None and single_month_block is None:
        return {
            "fee_year": "",
            "fee_latest_month": "",
            "fee_parse_status": "no_fee_block",
        }

    if annual_block is not None:
        title, fee_rows = annual_block
        by_code = {
            item.get("columnNm1"): item
            for item in fee_rows
            if isinstance(item, dict) and item.get("columnNm1")
        }

        def row_value(code: str, key: str) -> float | None:
            return parse_number(by_code.get(code, {}).get(key))

        latest_month = 0
        for month in range(1, 13):
            if any((row_value(code, f"mon{month}") or 0) != 0 for code in relevant_codes):
                latest_month = month

        title_text = " ".join(str(part) for part in title)
        year_match = re.search(r"(20\d{2})", title_text)
        out: dict[str, Any] = {
            "fee_year": year_match.group(1) if year_match else "",
            "fee_latest_month": str(latest_month) if latest_month else "",
            "fee_parse_status": "annual_monthly_ok",
        }
        for code, prefix in mapping.items():
            ytd = row_value(code, "mon13")
            out[f"{prefix}_ytd_krw"] = "" if ytd is None else str(int(ytd))
            latest = row_value(code, f"mon{latest_month}") if latest_month else None
            out[f"{prefix}_latest_month_krw"] = "" if latest is None else str(int(latest))
    else:
        title, fee_rows = single_month_block
        by_code = {
            item.get("columnNm1"): item
            for item in fee_rows
            if isinstance(item, dict) and item.get("columnNm1")
        }

        def row_value(code: str, key: str) -> float | None:
            return parse_number(by_code.get(code, {}).get(key))

        title_text = " ".join(str(part) for part in title)
        month_match = re.search(r"(20\d{4})", title_text)
        fee_month = month_match.group(1) if month_match else SEARCH_DATE
        out = {
            "fee_year": fee_month[:4],
            "fee_latest_month": fee_month[4:],
            "fee_parse_status": "single_month_ok",
        }
        for code, prefix in mapping.items():
            latest = row_value(code, "v0")
            out[f"{prefix}_ytd_krw"] = ""
            out[f"{prefix}_latest_month_krw"] = "" if latest is None else str(int(latest))
            unit_cost = row_value(code, "v1")
            out[f"{prefix}_latest_month_unit_krw_per_m2"] = "" if unit_cost is None else f"{unit_cost:.2f}"

    households = parse_number(household_count)
    heat = parse_number(out.get("heat_cost_ytd_krw"))
    hot = parse_number(out.get("hot_water_cost_ytd_krw"))
    if households and heat is not None:
        out["heat_cost_ytd_per_household_krw"] = f"{heat / households:.2f}"
    else:
        out["heat_cost_ytd_per_household_krw"] = ""
    if households and hot is not None:
        out["hot_water_cost_ytd_per_household_krw"] = f"{hot / households:.2f}"
    else:
        out["hot_water_cost_ytd_per_household_krw"] = ""
    return out


def parse_main_board_fee(payload: dict[str, Any], household_count: str) -> dict[str, Any]:
    monthly_amounts = [
        item for item in payload.get("aptMarketCostList", [])
        if isinstance(item, dict) and item.get("occuDate")
    ]
    monthly_units = [
        item for item in payload.get("aptFeeList", [])
        if isinstance(item, dict) and item.get("occuDate")
    ]
    if not monthly_amounts:
        return {
            "fee_year": "",
            "fee_latest_month": "",
            "fee_parse_status": "no_dashboard_fee_block",
        }

    monthly_amounts.sort(key=lambda item: str(item.get("occuDate", "")))
    monthly_units.sort(key=lambda item: str(item.get("occuDate", "")))

    def has_cost(item: dict[str, Any]) -> bool:
        return any((parse_number(item.get(key)) or 0) != 0 for key in ("publicTot", "privateTot", "sLevy"))

    cost_rows = [item for item in monthly_amounts if has_cost(item)]
    if not cost_rows:
        return {
            "fee_year": "",
            "fee_latest_month": "",
            "fee_parse_status": "dashboard_fee_empty",
        }

    latest = cost_rows[-1]
    latest_yyyymm = str(latest.get("occuDate", ""))
    unit_by_month = {str(item.get("occuDate", "")): item for item in monthly_units}
    latest_unit = unit_by_month.get(latest_yyyymm, {})

    def sum_krw(key: str) -> str:
        # K-APT dashboard amount chart uses thousand KRW for a selected complex.
        value = sum(parse_number(item.get(key)) or 0 for item in cost_rows)
        return str(int(round(value * 1000)))

    def latest_krw(key: str) -> str:
        value = parse_number(latest.get(key))
        return "" if value is None else str(int(round(value * 1000)))

    def unit_value(key: str) -> str:
        value = parse_number(latest_unit.get(key))
        return "" if value is None else f"{value:.2f}"

    public_ytd = parse_number(sum_krw("publicTot")) or 0
    private_ytd = parse_number(sum_krw("privateTot")) or 0
    levy_ytd = parse_number(sum_krw("sLevy")) or 0
    public_latest = parse_number(latest_krw("publicTot")) or 0
    private_latest = parse_number(latest_krw("privateTot")) or 0
    levy_latest = parse_number(latest_krw("sLevy")) or 0

    out: dict[str, Any] = {
        "fee_year": latest_yyyymm[:4],
        "fee_latest_month": latest_yyyymm[4:],
        "fee_parse_status": "dashboard_summary_ok",
        "fee_months_count": str(len(cost_rows)),
        "public_mgmt_cost_ytd_krw": str(int(public_ytd)),
        "private_usage_cost_ytd_krw": str(int(private_ytd)),
        "long_term_repair_reserve_ytd_krw": str(int(levy_ytd)),
        "total_mgmt_cost_ytd_krw": str(int(public_ytd + private_ytd + levy_ytd)),
        "public_mgmt_cost_latest_month_krw": str(int(public_latest)),
        "private_usage_cost_latest_month_krw": str(int(private_latest)),
        "long_term_repair_reserve_latest_month_krw": str(int(levy_latest)),
        "total_mgmt_cost_latest_month_krw": str(int(public_latest + private_latest + levy_latest)),
        "public_mgmt_cost_latest_month_unit_krw_per_m2": unit_value("publicTot"),
        "private_usage_cost_latest_month_unit_krw_per_m2": unit_value("privateTot"),
        "long_term_repair_reserve_latest_month_unit_krw_per_m2": unit_value("sLevy"),
    }

    total_unit = sum(parse_number(out.get(key)) or 0 for key in (
        "public_mgmt_cost_latest_month_unit_krw_per_m2",
        "private_usage_cost_latest_month_unit_krw_per_m2",
        "long_term_repair_reserve_latest_month_unit_krw_per_m2",
    ))
    out["total_mgmt_cost_latest_month_unit_krw_per_m2"] = f"{total_unit:.2f}" if total_unit else ""

    households = parse_number(household_count)
    if households:
        out["total_mgmt_cost_ytd_per_household_krw"] = f"{(public_ytd + private_ytd + levy_ytd) / households:.2f}"
    else:
        out["total_mgmt_cost_ytd_per_household_krw"] = ""
    return out


@dataclass
class Candidate:
    kaptCode: str
    kaptName: str
    bjdCode: str
    addr: str
    score: int
    keyword: str


class KaptClient:
    def __init__(self) -> None:
        self.cookiejar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookiejar))
        self.csrf = ""

    def request(self, path: str, data: dict[str, str] | None = None, referer: str | None = None) -> str:
        url = path if path.startswith("http") else BASE_URL + path
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        if "/cmmn/getMinViewAptInfo.do" in url:
            headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
            headers["X-Requested-With"] = "XMLHttpRequest"
        if referer:
            headers["Referer"] = referer
        if data is None:
            payload = None
        else:
            payload = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
            headers["X-Requested-With"] = "XMLHttpRequest"
        req = urllib.request.Request(url, data=payload, headers=headers)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with self.opener.open(req, timeout=30) as res:
                    raw = res.read()
                return raw.decode("utf-8", errors="replace")
            except urllib.error.HTTPError:
                raise
            except (
                urllib.error.URLError,
                TimeoutError,
                ConnectionResetError,
                http.client.RemoteDisconnected,
            ) as exc:
                last_error = exc
                time.sleep(0.8 * (attempt + 1))
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"request failed without response: {url}")

    def start(self) -> None:
        page = self.request("/web/main/index.do")
        self.csrf = extract_csrf(page)

    def search(self, keyword: str) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"keyword": keyword})
        text = self.request(f"/cmmn/getMinViewAptInfo.do?{query}", referer=BASE_URL + "/web/main/index.do")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []
        return payload.get("data", {}).get("list", []) or []

    def select_complex(self, kapt_code: str, bjd_code: str, go_url: str = "/kaptinfo/openkaptinfo.do") -> str:
        if not self.csrf:
            self.start()
        map_page = self.request(
            "/cmmn/knewMapView.do",
            {"go_url": go_url, "_csrf": self.csrf},
            referer=BASE_URL + "/web/main/index.do",
        )
        token = extract_csrf(map_page) or self.csrf
        page = self.request(
            "/cmmn/selectKapt.do",
            {
                "go_url": go_url,
                "bjd_code": bjd_code,
                "kapt_code": kapt_code,
                "search_date": SEARCH_DATE,
                "kapt_usedate": "",
                "kapt_name": "",
                "kaptDuty": "ALL",
                "_csrf": token,
            },
            referer=BASE_URL + "/cmmn/knewMapView.do",
        )
        self.csrf = extract_csrf(page) or token
        return page

    def post_selected_page(self, path: str) -> str:
        page = self.request(path, {"_csrf": self.csrf}, referer=BASE_URL + "/kaptinfo/openkaptinfo.do")
        self.csrf = extract_csrf(page) or self.csrf
        return page

    def management_detail(self, kapt_code: str) -> dict[str, Any]:
        text = self.request(
            "/kaptinfo/getKaptInfo_detail.do",
            {"kaptCode": kapt_code, "_csrf": self.csrf},
            referer=BASE_URL + "/kaptinfo/openKaptMng.do",
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

    def main_board(self, kapt_code: str, bjd_code: str, year: str = "2026") -> dict[str, Any]:
        text = self.request(
            "/cmmn/getMainBoard.do",
            {
                "searchYYYY": year,
                "searchDate": f"{year}01",
                "kaptCode": kapt_code,
                "comboKaptCode": kapt_code,
                "bjdCode": bjd_code,
                "kaptDuty": "ALL",
                "type": "BOTTOM",
                "_csrf": self.csrf,
            },
            referer=BASE_URL + "/apiinfo/goApiInfoSearch.do",
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}


def score_candidate(row: dict[str, str], item: dict[str, Any], keyword: str) -> int:
    raw_candidate_name = str(item.get("kaptName", ""))
    candidate_name = normalize(str(item.get("kaptName", "")))
    candidate_addr = normalize(str(item.get("addr", "")))
    row_names = [normalize(row.get("matched_name")), normalize(row.get("original_building_name")), normalize(row.get("building_name"))]
    row_addr = normalize(row.get("jibun_address"))
    row_dong = normalize(row.get("dong"))
    village, unit = extract_village_unit(row)
    keyword_norm = normalize(keyword)
    score = 0
    if any(candidate_name and (candidate_name in name or name in candidate_name) for name in row_names):
        score += 80
    if keyword_norm and (keyword_norm == candidate_name or keyword_norm in candidate_name):
        score += 30
    if any(keyword_norm and keyword_norm in name for name in row_names):
        score += 20
    if candidate_covers_unit(raw_candidate_name, village, unit):
        score += 90
    if row_addr and candidate_addr and (candidate_addr in row_addr or row_addr in candidate_addr):
        score += 50
    if row_dong and row_dong in candidate_addr:
        score += 10
    if str(item.get("bjdCode", "")).startswith("36110"):
        score += 10
    if "관리사무소" in raw_candidate_name:
        score -= 100
    return score


def find_best_candidate(client: KaptClient, row: dict[str, str]) -> Candidate | None:
    best: Candidate | None = None
    for keyword in keyword_candidates(row):
        try:
            items = client.search(keyword)
        except (urllib.error.URLError, TimeoutError):
            items = []
        for item in items:
            score = score_candidate(row, item, keyword)
            candidate = Candidate(
                kaptCode=str(item.get("kaptCode", "")),
                kaptName=str(item.get("kaptName", "")),
                bjdCode=str(item.get("bjdCode", "")),
                addr=str(item.get("addr", "")),
                score=score,
                keyword=keyword,
            )
            if candidate.kaptCode and (best is None or candidate.score > best.score):
                best = candidate
        time.sleep(REQUEST_SLEEP_SEC)
    return best


def management_fields(detail: dict[str, Any]) -> dict[str, Any]:
    kapt = detail.get("resultMap_kapt") or {}
    car = detail.get("getKaptdfCarInfo") or {}
    return {
        "building_structure": kapt.get("codeStr", ""),
        "electric_capacity_kw": kapt.get("kaptdEcapa", ""),
        "electric_contract_type": kapt.get("codeEcon", ""),
        "electric_safety_manager_type": kapt.get("codeEmgr", ""),
        "fire_alarm_type": kapt.get("codeFalarm", ""),
        "water_supply_type": kapt.get("codeWsupply", ""),
        "elevator_management_type": kapt.get("codeElev", ""),
        "elevator_count": kapt.get("kaptdEcntTotal", ""),
        "parking_ground_count": kapt.get("kaptdPcnt", ""),
        "parking_underground_count": kapt.get("kaptdPcntu", ""),
        "parking_total_count": str((parse_number(kapt.get("kaptdPcnt")) or 0) + (parse_number(kapt.get("kaptdPcntu")) or 0)).rstrip(".0"),
        "cctv_count": kapt.get("kaptdCccnt", ""),
        "welfare_facility": str(kapt.get("welfareFacility", "")).replace("()", ",").strip(","),
        "home_network": kapt.get("codeNet", ""),
        "registered_vehicle_count": car.get("carTot", ""),
        "registered_ev_count": car.get("carTotEl", ""),
        "ev_charger_ground_installed": "Y" if car.get("elisGrdYn") == "Y" else "",
        "ev_charger_underground_installed": "Y" if car.get("elisUngYn") == "Y" else "",
        "ev_parking_ground_count": car.get("elnpGrd", ""),
        "ev_parking_underground_count": car.get("elnpUng", ""),
    }


def enrich() -> int:
    clear_generated_raw_pages()
    rows = read_csv_rows(INPUT_CSV)
    client = KaptClient()
    client.start()
    enriched_rows: list[dict[str, Any]] = []
    match_rows: list[dict[str, Any]] = []

    for idx, row in enumerate(rows, 1):
        substation_id = row.get("substation_id", str(idx))
        candidate = find_best_candidate(client, row)
        match_info: dict[str, Any] = {
            "substation_id": substation_id,
            "input_name": row.get("matched_name") or row.get("building_name"),
            "match_status": "unmatched",
            "kapt_code": "",
            "kapt_name": "",
            "kapt_bjd_code": "",
            "kapt_addr": "",
            "match_score": "",
            "matched_keyword": "",
        }
        output = dict(row)
        output.update(
            {
                "district_heating_supply_confirmed": "Y",
                "district_heating_supplier": "한국지역난방공사",
                "district_heating_supply_basis": "한국지역난방공사 건물별 지역난방 공급현황 정보_20221231 원천 CSV에서 세종 1생활권 아파트 후보를 선별",
                "external_geocode_source": "Kakao Map place search",
                "kapt_match_status": "unmatched",
            }
        )

        if candidate is not None and candidate.score >= 100:
            match_info.update(
                {
                    "match_status": "matched",
                    "kapt_code": candidate.kaptCode,
                    "kapt_name": candidate.kaptName,
                    "kapt_bjd_code": candidate.bjdCode,
                    "kapt_addr": candidate.addr,
                    "match_score": candidate.score,
                    "matched_keyword": candidate.keyword,
                }
            )
            try:
                basic_page = client.select_complex(candidate.kaptCode, candidate.bjdCode)
                (RAW_DIR / f"{int(substation_id):02d}_{candidate.kaptCode}_basic.html").write_text(
                    basic_page,
                    encoding="utf-8",
                )
                basic = parse_basic_page(basic_page)
                output.update(
                    {
                        "kapt_match_status": "matched",
                        "kapt_code": candidate.kaptCode,
                        "kapt_bjd_code": candidate.bjdCode,
                        "kapt_search_name": candidate.kaptName,
                        "kapt_search_address": candidate.addr,
                        "kapt_match_score": str(candidate.score),
                        "kapt_matched_keyword": candidate.keyword,
                    }
                )
                output.update(basic)

                client.post_selected_page("/kaptinfo/openKaptMng.do")
                detail = client.management_detail(candidate.kaptCode)
                output.update(management_fields(detail))

                fee_client = KaptClient()
                fee_client.start()
                fee_page = fee_client.select_complex(
                    candidate.kaptCode,
                    candidate.bjdCode,
                    go_url="/apiinfo/goApiInfoSearch.do",
                )
                (RAW_DIR / f"{int(substation_id):02d}_{candidate.kaptCode}_fee.html").write_text(
                    fee_page,
                    encoding="utf-8",
                )
                fee_result = parse_fee_page(fee_page, str(output.get("household_count", "")))
                if fee_result.get("fee_parse_status") in {"no_fee_block", "no_monthly_fee_block"}:
                    main_board = fee_client.main_board(candidate.kaptCode, candidate.bjdCode)
                    (RAW_DIR / f"{int(substation_id):02d}_{candidate.kaptCode}_main_board.json").write_text(
                        json.dumps(main_board, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    fee_result = parse_main_board_fee(main_board, str(output.get("household_count", "")))
                output.update(fee_result)
            except Exception as exc:  # Keep row-level failures auditable without stopping all 31.
                output["kapt_match_status"] = "matched_fetch_failed"
                output["kapt_fetch_error"] = repr(exc)
        else:
            output["kapt_fetch_error"] = "no candidate over threshold"

        enriched_rows.append(output)
        match_rows.append(match_info)
        print(
            f"[{idx:02d}/{len(rows)}] substation={substation_id} "
            f"status={output.get('kapt_match_status')} kapt={output.get('kapt_code', '')}",
            flush=True,
        )
        time.sleep(REQUEST_SLEEP_SEC)

    original_fields = list(rows[0].keys()) if rows else []
    extra_fields = [
        "district_heating_supply_confirmed",
        "district_heating_supplier",
        "district_heating_supply_basis",
        "external_geocode_source",
        "kapt_match_status",
        "kapt_code",
        "kapt_bjd_code",
        "kapt_search_name",
        "kapt_search_address",
        "kapt_match_score",
        "kapt_matched_keyword",
        "kapt_name",
        "kapt_code_from_basic",
        "kapt_complex_type",
        "kapt_legal_address",
        "kapt_road_address",
        "sale_type",
        "management_type",
        "heating_type",
        "corridor_type",
        "gross_floor_area_m2",
        "approval_date",
        "building_count",
        "household_count",
        "exclusive_residential_area_m2",
        "kapt_join_date",
        "exclusive_area_households_json",
        "builder_developer",
        "building_structure",
        "electric_capacity_kw",
        "electric_contract_type",
        "electric_safety_manager_type",
        "fire_alarm_type",
        "water_supply_type",
        "elevator_management_type",
        "elevator_count",
        "parking_ground_count",
        "parking_underground_count",
        "parking_total_count",
        "cctv_count",
        "welfare_facility",
        "home_network",
        "registered_vehicle_count",
        "registered_ev_count",
        "ev_charger_ground_installed",
        "ev_charger_underground_installed",
        "ev_parking_ground_count",
        "ev_parking_underground_count",
        "fee_year",
        "fee_latest_month",
        "fee_parse_status",
        "fee_months_count",
        "public_mgmt_cost_ytd_krw",
        "public_mgmt_cost_latest_month_krw",
        "public_mgmt_cost_latest_month_unit_krw_per_m2",
        "private_usage_cost_ytd_krw",
        "private_usage_cost_latest_month_krw",
        "private_usage_cost_latest_month_unit_krw_per_m2",
        "heat_cost_ytd_krw",
        "heat_public_cost_ytd_krw",
        "heat_private_cost_ytd_krw",
        "hot_water_cost_ytd_krw",
        "hot_water_public_cost_ytd_krw",
        "hot_water_private_cost_ytd_krw",
        "gas_cost_ytd_krw",
        "electricity_cost_ytd_krw",
        "water_cost_ytd_krw",
        "long_term_repair_reserve_ytd_krw",
        "long_term_repair_reserve_latest_month_krw",
        "long_term_repair_reserve_latest_month_unit_krw_per_m2",
        "total_mgmt_cost_ytd_krw",
        "heat_cost_latest_month_krw",
        "heat_cost_latest_month_unit_krw_per_m2",
        "hot_water_cost_latest_month_krw",
        "hot_water_cost_latest_month_unit_krw_per_m2",
        "electricity_cost_latest_month_krw",
        "electricity_cost_latest_month_unit_krw_per_m2",
        "total_mgmt_cost_latest_month_krw",
        "total_mgmt_cost_latest_month_unit_krw_per_m2",
        "total_mgmt_cost_ytd_per_household_krw",
        "heat_cost_ytd_per_household_krw",
        "hot_water_cost_ytd_per_household_krw",
        "kapt_fetch_error",
    ]
    fieldnames = original_fields + [field for field in extra_fields if field not in original_fields]
    write_csv(OUTPUT_CSV, enriched_rows, fieldnames)
    write_csv(
        MATCH_CSV,
        match_rows,
        [
            "substation_id",
            "input_name",
            "match_status",
            "kapt_code",
            "kapt_name",
            "kapt_bjd_code",
            "kapt_addr",
            "match_score",
            "matched_keyword",
        ],
    )
    META_JSON.write_text(
        json.dumps(
            {
                "generated_outputs": {
                    "enriched_csv": str(OUTPUT_CSV.relative_to(ROOT)),
                    "match_csv": str(MATCH_CSV.relative_to(ROOT)),
                    "raw_kapt_pages_dir": str(RAW_DIR.relative_to(ROOT)),
                },
                "sources": [
                    {
                        "name": "K-APT 공동주택관리정보시스템",
                        "url": "https://www.k-apt.go.kr/",
                        "used_for": [
                            "단지명 검색 및 kaptCode 매칭",
                            "단지 기본정보",
                            "관리시설정보",
                            "우리단지 월별 관리비 대시보드 요약",
                        ],
                    },
                    {
                        "name": "국토교통부_공동주택 단지 기본 정보",
                        "url": "https://www.data.go.kr/data/15073271/fileData.do",
                        "used_for": ["K-APT 기본정보 항목 정의 확인"],
                    },
                    {
                        "name": "국토교통부_공동주택 단지 관리비 정보",
                        "url": "https://www.data.go.kr/data/3039714/fileData.do",
                        "used_for": ["K-APT 관리비 공개 데이터 항목 정의 확인"],
                    },
                    {
                        "name": "한국지역난방공사_건물별 지역난방 공급현황 정보_20221231",
                        "url": "local:C:/Users/Admin/Downloads/한국지역난방공사_건물별 지역난방 공급현황 정보_20221231 (1).csv",
                        "used_for": ["세종 1생활권 지역난방 공급 아파트 후보 선별"],
                    },
                    {
                        "name": "Kakao Map place search",
                        "url": "https://map.kakao.com/",
                        "used_for": ["도로명주소, 지번주소, 위도, 경도 보강"],
                    },
                ],
                "notes": [
                    "K-APT 파일 일괄 다운로드 URL은 직접 호출 시 차단되어 공개 화면 조회 흐름으로 수집했다.",
                    "공공데이터포털 OpenAPI 상세 조회는 serviceKey가 없어 사용하지 않았다.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(enrich())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
