# HeatGrid Weather Data

이 폴더는 기상청 API허브 ASOS 시간자료를 HeatGrid Agent 답변 생성에 붙이기 위한 전용 공간입니다.

## Folder Boundary

- `data/weather/samples/`: API 연동 확인용 샘플 응답과 weather context JSON
- `data/weather/cache/`: 운영 중 API 응답 캐시 또는 DB 적재 전 임시 파일
- `src/heatgrid_weather/`: 기상청 API client와 weather context 판단 로직
- `scripts/weather/`: 수동 실행 및 검증용 스크립트

RAG 문서는 `data/rag_sources/`에만 둡니다.
세종 아파트/K-APT/PreDist 외부 매핑 데이터는 `data/external/`에만 둡니다.
기상청 API 결과는 `data/weather/` 아래에만 둡니다.

## Usage

API key는 코드나 CSV에 저장하지 않고 환경변수로만 주입합니다.

기상청 API허브에서 다음 API 활용신청이 필요합니다.

```text
지상관측 > 종관기상관측(ASOS) > 지상 관측자료 조회 > 시간자료(기간 조회) API
endpoint: /api/typ01/url/kma_sfctm3.php
parameter: tm1, tm2, stn, help, authKey
```

월간/기간 리포트용 일 단위 요약까지 사용하려면 다음 API도 활용신청합니다.

```text
지상관측 > 종관기상관측(ASOS) > 지상 관측자료 조회 > 일자료(기간 조회) API
endpoint: /api/typ01/url/kma_sfcdd3.php
parameter: tm1, tm2, stn, help, authKey
```

```powershell
$env:KMA_SERVICE_KEY = "<기상청 API허브 인증키>"
.\\.venv\\Scripts\\python.exe scripts\\weather\\fetch_weather_context.py `
  --start "2019-12-01 00:00:00" `
  --end "2019-12-01 06:00:00" `
  --output data\\weather\\samples\\sejong_weather_context_sample.json
```

일자료 기간 요약:

```powershell
$env:KMA_SERVICE_KEY = "<기상청 API허브 인증키>"
.\\.venv\\Scripts\\python.exe scripts\\weather\\fetch_daily_weather_summary.py `
  --start-date "2019-12-01" `
  --end-date "2019-12-07" `
  --output data\\weather\\samples\\sejong_daily_weather_summary_sample.json
```

## Agent Tool Role

`get_weather_context(window_start, window_end, region="세종")` 형태의 LangGraph tool로 연결합니다.

이 tool은 기상청 API허브 ASOS 시간자료 기간 조회 API를 호출하고 다음 값을 반환합니다.

- 평균/최저/최고 기온
- 전일 동시간대 대비 기온 변화
- 강수량
- 적설
- 습도
- 풍속
- 난방도시 기반 난방 부하 가능성
- 기상 관련성 수준
- Agent 답변용 해석 문장

기상 요인은 고장 원인 확정 근거가 아니라 운영 부하 맥락 보조 근거로만 사용합니다.

월간 리포트나 기간 요약에는 `get_daily_weather_summary(start_date, end_date, region="세종")` 형태로 연결합니다.
