import React, { useCallback, useEffect, useState } from 'react';
import type { Gate } from '../api';
import { listGates } from '../api';
import { GateQueue } from './GateQueue';
import { GateDetail } from './GateDetail';

const colors = {
  bg: '#0b0f19',
  bgElevated: '#141a28',
  border: '#2a3548',
  text: '#f4f6fb',
  textMuted: '#a8b3c7',
  accent: '#7c5cff',
};

const DEFAULT_APPROVER = 'human.ui';

export function ApprovalsPage() {
  const [pending, setPending] = useState<Gate[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Gate | null>(null);
  const [approverId, setApproverId] = useState(DEFAULT_APPROVER);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const data = await listGates();
      setPending(data.pending || []);
      setLoading(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selectedId) {
      setSelected(null);
      return;
    }
    const fromList = pending.find((g) => g.id === selectedId);
    if (fromList) setSelected(fromList);
  }, [selectedId, pending]);

  function onUpdated(gate: Gate) {
    setSelected(gate);
    if (gate.status !== 'pending') {
      setPending((prev) => prev.filter((g) => g.id !== gate.id));
      setSelectedId(null);
      setSelected(null);
    } else {
      setPending((prev) => prev.map((g) => (g.id === gate.id ? gate : g)));
    }
    void refresh();
  }

  return (
    <div style={{ minHeight: '100vh', background: colors.bg, color: colors.text }}>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '16px 24px',
          background: colors.bgElevated,
          borderBottom: `1px solid ${colors.border}`,
        }}
      >
        <strong style={{ color: colors.accent }}>HighlightAI</strong>
        <span style={{ color: colors.textMuted }}>Approvals</span>
        <label
          style={{
            marginLeft: 'auto',
            fontSize: 13,
            color: colors.textMuted,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          Approver
          <input
            value={approverId}
            onChange={(e) => setApproverId(e.target.value)}
            style={{
              background: colors.bg,
              color: colors.text,
              border: `1px solid ${colors.border}`,
              borderRadius: 6,
              padding: '6px 10px',
            }}
          />
        </label>
        <button
          type="button"
          onClick={() => void refresh()}
          style={{
            background: colors.accent,
            color: '#fff',
            border: 'none',
            borderRadius: 6,
            padding: '6px 12px',
            cursor: 'pointer',
            fontWeight: 600,
          }}
        >
          Refresh
        </button>
      </header>

      <main
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(240px, 320px) 1fr',
          gap: 20,
          maxWidth: 1100,
          margin: '0 auto',
          padding: 24,
        }}
      >
        <aside>
          <h1 style={{ fontSize: 18, marginTop: 0 }}>Pending queue</h1>
          {loading ? (
            <p style={{ color: colors.textMuted }}>Loading…</p>
          ) : (
            <GateQueue gates={pending} selectedId={selectedId} onSelect={setSelectedId} />
          )}
          {error ? (
            <p role="alert" style={{ color: '#ff5c7c', fontSize: 13 }}>
              {error}
            </p>
          ) : null}
        </aside>
        <section>
          <GateDetail gate={selected} approverId={approverId} onUpdated={onUpdated} />
        </section>
      </main>
    </div>
  );
}

export default ApprovalsPage;
