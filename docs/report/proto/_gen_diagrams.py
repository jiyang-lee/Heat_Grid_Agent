"""단계별 보고서용 SVG 다이어그램 생성기.

일관된 스타일로 커밋(단계)별 흐름도를 만든다. <img>로 임베드되어도 보이도록
색은 var(--...) + hex 폴백을 쓰고, 다크모드는 @media로 처리한다.

실행: uv run python docs/report/proto/_gen_diagrams.py
"""

from __future__ import annotations

import xml.dom.minidom as minidom
from pathlib import Path

OUT = Path(__file__).resolve().parent / "img"

STYLE = """
  <style>
    svg{--acc-src:#3b6db5;--acc-src-bg:#eaf1fb;--acc-mine:#2e9e6b;--acc-mine-bg:#e8f6ef;
        --ink:var(--color-text-primary,#1f2328);--ink2:var(--color-text-secondary,#57606a);
        --card:var(--color-background-primary,#ffffff);--line:var(--color-border-secondary,#d0d7de);}
    @media (prefers-color-scheme:dark){svg{--acc-src-bg:#16263d;--acc-mine-bg:#10301f;--card:#0d1117;--line:#30363d;}}
    text{font-family:var(--font-sans,system-ui);fill:var(--ink);}
    .h{font-size:16px;font-weight:500;}
    .t{font-size:12.5px;font-weight:500;}
    .s{font-size:11px;fill:var(--ink2);}
    .box{fill:var(--card);stroke:var(--line);stroke-width:1.2;}
    .src{fill:var(--acc-src-bg);stroke:var(--acc-src);stroke-width:1.2;}
    .mine{fill:var(--acc-mine-bg);stroke:var(--acc-mine);stroke-width:1.2;}
    .edge{stroke:var(--ink2);stroke-width:1.5;fill:none;marker-end:url(#ah);}
  </style>
"""

MARKER = """
  <defs>
    <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0,0 L10,5 L0,10 z" fill="var(--color-text-secondary,#57606a)"/>
    </marker>
  </defs>
"""

X0, Y0 = 20, 64
COLW, ROWH = 196, 108
BW, BH = 170, 62


def _cx(col):
    return X0 + col * COLW + BW / 2


def _cy(row):
    return Y0 + row * ROWH + BH / 2


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(title, nodes, edges, footer):
    ncols = max(n["col"] for n in nodes) + 1
    nrows = max(n["row"] for n in nodes) + 1
    width = X0 * 2 + (ncols - 1) * COLW + BW
    height = Y0 + nrows * ROWH + 26
    by_id = {n["id"]: n for n in nodes}

    parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="{_esc(title)}">',
        MARKER,
        STYLE,
        f'<text x="{X0}" y="30" class="h">{_esc(title)}</text>',
    ]

    # edges first (under boxes)
    for e in edges:
        s, d = by_id[e[0]], by_id[e[1]]
        dashed = ' stroke-dasharray="4 3"' if len(e) > 2 and e[2] else ""
        sx, sy = _cx(s["col"]), _cy(s["row"])
        dx, dy = _cx(d["col"]), _cy(d["row"])
        if s["row"] == d["row"] and d["col"] > s["col"]:
            x1, y1 = X0 + s["col"] * COLW + BW, sy
            x2, y2 = X0 + d["col"] * COLW, dy
            path = f"M{x1},{y1} L{x2-2},{y2}"
        elif s["col"] == d["col"] and d["row"] > s["row"]:
            path = f"M{sx},{Y0+s['row']*ROWH+BH} L{sx},{Y0+d['row']*ROWH-2}"
        else:
            midy = (Y0 + s["row"] * ROWH + BH + Y0 + d["row"] * ROWH) / 2 if d["row"] > s["row"] else (sy + dy) / 2
            y1 = Y0 + s["row"] * ROWH + BH if d["row"] > s["row"] else sy
            y2 = Y0 + d["row"] * ROWH - 2 if d["row"] > s["row"] else dy
            path = f"M{sx},{y1} L{sx},{midy} L{dx},{midy} L{dx},{y2}"
        parts.append(f'<path class="edge" d="{path}"{dashed}/>')

    # boxes
    for n in nodes:
        x = X0 + n["col"] * COLW
        y = Y0 + n["row"] * ROWH
        cls = n.get("kind", "box")
        parts.append(f'<rect class="{cls}" x="{x}" y="{y}" width="{BW}" height="{BH}" rx="8"/>')
        parts.append(f'<text x="{x+BW/2}" y="{y+25}" class="t" text-anchor="middle">{_esc(n["label"])}</text>')
        if n.get("sub"):
            parts.append(f'<text x="{x+BW/2}" y="{y+43}" class="s" text-anchor="middle">{_esc(n["sub"])}</text>')

    if footer:
        parts.append(f'<text x="{X0}" y="{height-9}" class="s">{_esc(footer)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


DIAGRAMS = {
    "01_asset_transfer": dict(
        title="S0. 자산 이전 (43e2772)",
        nodes=[
            {"id": "a1", "col": 0, "row": 0, "kind": "src", "label": "agent1", "sub": "raw→전처리"},
            {"id": "m1", "col": 0, "row": 1, "kind": "src", "label": "mlmodel1", "sub": "ML output·handoff"},
            {"id": "proto", "col": 1, "row": 0, "kind": "mine", "label": "proto 브랜치", "sub": "신규 작업 베이스"},
            {"id": "sch", "col": 2, "row": 0, "kind": "box", "label": "schema 000-005", "sub": "+ contracts 01-04"},
            {"id": "hand", "col": 2, "row": 1, "kind": "box", "label": "model_handoff", "sub": "13 파일"},
        ],
        edges=[("a1", "proto"), ("m1", "proto"), ("proto", "sch"), ("proto", "hand")],
        footer="이전: DDL 6 · JSON 5 · contracts 4 · handoff 13 (출처 위계 준수, 변경 금지)",
    ),
    "02_contract": dict(
        title="A. Priority 계약 + 목 데이터 (04b5d41)",
        nodes=[
            {"id": "ct", "col": 0, "row": 0, "kind": "mine", "label": "계약 3종", "sub": "006 DDL·schema·README"},
            {"id": "gen", "col": 0, "row": 1, "kind": "mine", "label": "generate_mock", "sub": "Codex 대역"},
            {"id": "mock", "col": 1, "row": 1, "kind": "box", "label": "mock_ml_output", "sub": "300행·25컬럼"},
            {"id": "gate", "col": 2, "row": 0, "kind": "mine", "label": "validate_contracts", "sub": "검증 게이트"},
        ],
        edges=[("gen", "mock"), ("ct", "gate"), ("mock", "gate")],
        footer="정상 161 / 고장전조 139 · 검증: JSON 6 · DDL 7 · PK 유니크",
    ),
    "03_model": dict(
        title="B. Priority 모델 — LGBM 회귀 (3e5092d)",
        nodes=[
            {"id": "mock", "col": 0, "row": 0, "kind": "box", "label": "mock 300행", "sub": "라벨 0/33/66/100"},
            {"id": "tr", "col": 1, "row": 0, "kind": "box", "label": "train 196", "sub": "양성 95"},
            {"id": "ho", "col": 1, "row": 1, "kind": "box", "label": "holdout 104", "sub": "양성 R=44"},
            {"id": "lgbm", "col": 2, "row": 0, "kind": "mine", "label": "LGBMRegressor", "sub": "7피처·정규화"},
            {"id": "ev", "col": 3, "row": 0, "kind": "mine", "label": "evaluate", "sub": "precision@k·NDCG"},
            {"id": "rule", "col": 3, "row": 1, "kind": "src", "label": "rule v2", "sub": "baseline"},
            {"id": "art", "col": 4, "row": 0, "kind": "mine", "label": "model.joblib", "sub": "+ metadata"},
        ],
        edges=[("mock", "tr"), ("mock", "ho"), ("tr", "lgbm"), ("lgbm", "ev"), ("ho", "ev"), ("rule", "ev"), ("ev", "art")],
        footer="precision@10/20/44 = 1.00 · NDCG = 1.00 · rule v2 동등 이상 → 채택",
    ),
    "04_agent": dict(
        title="C. LLM/Tool 에이전트 — langgraph (fad501b)",
        nodes=[
            {"id": "start", "col": 0, "row": 0, "kind": "box", "label": "START", "sub": "상위 N 시드"},
            {"id": "llm", "col": 1, "row": 0, "kind": "mine", "label": "llm 노드", "sub": "ChatOpenAI"},
            {"id": "tools", "col": 2, "row": 0, "kind": "mine", "label": "ToolNode", "sub": "5 tools"},
            {"id": "end", "col": 3, "row": 0, "kind": "box", "label": "END", "sub": "초안 보고"},
            {"id": "docs", "col": 2, "row": 1, "kind": "mine", "label": "docs/send", "sub": "보고서+메일 5+5"},
        ],
        edges=[("start", "llm"), ("llm", "tools"), ("tools", "llm", True), ("llm", "end"), ("tools", "docs")],
        footer="고장 단정 금지 · 운영자 검토 전제 · 자동 발송 없음",
    ),
    "05_serve": dict(
        title="D. 서버 / 프론트 (2fe5d81)",
        nodes=[
            {"id": "ps", "col": 0, "row": 0, "kind": "box", "label": "priority_scores", "sub": "csv"},
            {"id": "docs", "col": 0, "row": 1, "kind": "box", "label": "docs/send", "sub": "초안 md"},
            {"id": "api", "col": 1, "row": 0, "kind": "mine", "label": "FastAPI", "sub": "REST 3 (읽기전용)"},
            {"id": "fe", "col": 2, "row": 0, "kind": "mine", "label": "React + Vite", "sub": "표→상세→초안"},
        ],
        edges=[("ps", "api"), ("docs", "api"), ("api", "fe")],
        footer="엔드포인트 3 · 표 50행 렌더 · 발송 엔드포인트 없음",
    ),
    "06_validate": dict(
        title="V. 검증 스냅샷 (4143cd1)",
        nodes=[
            {"id": "run", "col": 0, "row": 0, "kind": "box", "label": "전 사이클 재실행", "sub": "재현성"},
            {"id": "chain", "col": 1, "row": 0, "kind": "mine", "label": "mock→학습→추론", "sub": "→에이전트"},
            {"id": "test", "col": 2, "row": 0, "kind": "mine", "label": "pytest", "sub": "6 passed"},
        ],
        edges=[("run", "chain"), ("chain", "test")],
        footer="목데이터 한 사이클 재현 + 전처리 테스트 통과",
    ),
    "07_bugfix": dict(
        title="F. 버그픽스 — 키 충돌 (8c1b3a5)",
        nodes=[
            {"id": "sym", "col": 0, "row": 0, "kind": "box", "label": "React dup key", "sub": "증상"},
            {"id": "c1", "col": 1, "row": 0, "kind": "box", "label": "원인 1", "sub": "키에 manufacturer 누락"},
            {"id": "c2", "col": 1, "row": 1, "kind": "box", "label": "원인 2", "sub": "목데이터 PK 중복"},
            {"id": "fix", "col": 2, "row": 0, "kind": "mine", "label": "make_key 공용화", "sub": "+ 유니크 보장"},
            {"id": "gate", "col": 3, "row": 0, "kind": "mine", "label": "PK 중복 검사", "sub": "게이트 추가"},
        ],
        edges=[("sym", "c1"), ("sym", "c2"), ("c1", "fix"), ("c2", "fix"), ("fix", "gate")],
        footer="수정 후 PK 중복 0 · make_key 300개 유니크 · 50행 누락 없음",
    ),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, spec in DIAGRAMS.items():
        svg = render(spec["title"], spec["nodes"], spec["edges"], spec["footer"])
        minidom.parseString(svg)  # XML 유효성 검증
        (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")
        print(f"wrote {name}.svg ({len(spec['nodes'])} nodes)")


if __name__ == "__main__":
    main()
