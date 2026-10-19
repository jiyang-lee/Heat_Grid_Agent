# Public sample demo

Build: `npm ci` then `npm run build:demo`. Serve `dist-demo/` as static files (relative asset base supports a subdirectory). `VITE_DEMO_MODE=true` is the only mode switch; `.env.demo` contains this public boolean. Production uses `npm run build` unchanged. The existing Vercel rewrite supports deep paths; demo navigation uses hash links and survives refresh on static hosts.

The demo never mounts the production App or its query/scenario/map contexts. It contains a local provider and system Korean sans fonts, locally bundled brand asset and saved JSON. No backend, database, LLM, external map, telemetry or analytics calls are made. Reset restores the equipment screen and fault scenario; no local storage is written.

## Fixture provenance and review

Source: public repository `jiyang-lee/Heat_Grid_Agent`, `output/ops_agent/cases/pump_failure_urgent_with_rag.json`. `src/demo/saved-report.json` is copied byte-for-byte. The report has public apartment/site context, diagnostic signals, a score, action/caution arrays and tool names. It has no person, contact, credential, private endpoint or token. Tool names describe the original run; they are not called by this demo. The report's original wording is displayed as a saved example, not a new production outcome. No sensor series or completion metrics have been invented. Normal mode is explicitly a UI empty-state example, not an asserted measured normal result.

The source's own operator_review field is visible only inside the original JSON; the demo does not turn it into operational approval. Read original safety cautions in the report. The static network is a labelled conceptual diagram rather than a geographic map.

Validation: `npm run typecheck`, `npm run lint`, `npm run build:demo`; run `VITE_DEMO_MODE=true npm run test:e2e -- e2e/demo.spec.ts` (PowerShell: set `$env:VITE_DEMO_MODE='true'` first). E2E checks the equipment→alert→evidence→saved report journey, refresh, normal state, reset, horizontal overflow and network origin/API isolation.


Fixture source commit: `51d680d55cce6dfdce72be001cd451aba19d00c0`. SHA256 (both original and copied fixture): `9ABAB0CC918F2E70AD7B36326A87C1886BC79B2C7DD46D9415B109E698DEFDB2`.
For a dedicated Vercel sample deployment from frontend/, use `vercel --local-config vercel.demo.json`; the normal vercel.json remains unchanged. This task has not deployed it.
