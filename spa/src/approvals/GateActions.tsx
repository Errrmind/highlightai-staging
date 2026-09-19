import React, { useState } from 'react';
import type { Gate } from '../api';
import { approveGate, rejectGate, requestMoreInfo } from '../api';

const colors = {
  bgElevated: '#141a28',
  border: '#2a3548',
  text: '#f4f6fb',
  textMuted: '#a8b3c7',
  accent: '#7c5cff',
  danger: '#ff5c7c',
  warn: '#ffb020',
};

export type GateActionsProps = {
  gate: Gate;
  approverId: string;
  onUpdated: (gate: Gate) => void;
};

export function GateActions({ gate, approverId, onUpdated }: GateActionsProps) {
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (gate.status !== 'pending') {
    return (
      <p style={{ color: colors.textMuted }}>
        Gate is <strong style={{ color: colors.text }}>{gate.status}</strong> — actions disabled.
      </p>
    );
  }

  async function run(action: 'approve' | 'reject' | 'more-info') {
    setError(null);
    setBusy(true);
    try {
      let next: Gate;
      if (action === 'approve') {
        next = await approveGate(gate.id, {
          approver_id: approverId,
          comment: comment.trim() || undefined,
        });
      } else if (action === 'reject') {
        if (!comment.trim()) {
          setError('Reject requires a non-empty rationale.');
          setBusy(false);
          return;
        }
        next = await rejectGate(gate.id, {
          approver_id: approverId,
          comment: comment.trim(),
        });
      } else {
        if (!comment.trim()) {
          setError('More-info requires a comment.');
          setBusy(false);
          return;
        }
        next = await requestMoreInfo(gate.id, {
          approver_id: approverId,
          comment: comment.trim(),
        });
      }
      setComment('');
      onUpdated(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const btnBase: React.CSSProperties = {
    padding: '10px 16px',
    borderRadius: 8,
    border: 'none',
    cursor: busy ? 'wait' : 'pointer',
    fontWeight: 600,
    opacity: busy ? 0.7 : 1,
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <label style={{ color: colors.textMuted, fontSize: 13 }}>
        Comment / rationale
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={3}
          placeholder="Approve: optional · Reject / More-info: required"
          style={{
            display: 'block',
            width: '100%',
            marginTop: 6,
            boxSizing: 'border-box',
            background: colors.bgElevated,
            color: colors.text,
            border: `1px solid ${colors.border}`,
            borderRadius: 8,
            padding: 10,
            fontFamily: 'inherit',
          }}
        />
      </label>
      {error ? (
        <div role="alert" style={{ color: colors.danger, fontSize: 13 }}>
          {error}
        </div>
      ) : null}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        <button
          type="button"
          disabled={busy}
          onClick={() => run('approve')}
          style={{ ...btnBase, background: colors.accent, color: '#fff' }}
        >
          Approve
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => run('reject')}
          style={{ ...btnBase, background: colors.danger, color: '#fff' }}
        >
          Reject
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => run('more-info')}
          style={{
            ...btnBase,
            background: colors.bgElevated,
            color: colors.warn,
            border: `1px solid ${colors.border}`,
          }}
        >
          Request more info
        </button>
      </div>
    </div>
  );
}

export default GateActions;
