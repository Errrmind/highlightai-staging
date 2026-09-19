# HighlightAI Approvals SPA

Vite + React (ESM) UI for **Human Gate** approvals. Brand tokens match Formatter `ReportShell` (`#0b0f19` bg, `#7c5cff` accent).

## Layout

```
spa/
  index.html
  src/
    main.tsx
    App.tsx
    api.ts                 # /humangate client
    approvals/
      index.ts             # public exports
      ApprovalsPage.tsx
      GateQueue.tsx
      GateDetail.tsx
      GateActions.tsx
```

## Scripts

```bash
cd /workspace/highlightai/services/orchestrator/spa
npm install
npm run build    # tsc --noEmit && vite build → dist/
npm run dev      # proxies /humangate → http://127.0.0.1:18765
```

## Behavior

| Action | Comment |
|---|---|
| Approve | Optional |
| Reject | **Required** rationale (API 400 if empty) |
| More info | **Required** comment; gate stays `pending` |

Shows quorum progress (`approvals.length / required_approvals`) and a banner when `escalation_target=manager`.

## Env

- `VITE_HUMANGATE_BASE` — API prefix (default `/humangate`)
