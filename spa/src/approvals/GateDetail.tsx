import React from 'react';
import type { Gate } from '../api';
import { quorumProgress } from '../api';
import { GateActions } from './GateActions';

const colors = {
  bgCard: '#1a2236',
  bgElevated: '#141a28',
  border: '#2a3548',
  text: '#f4f6fb',
  textMuted: '#a8b3c7',
  accent: '#7c5cff',
  warn: '#ffb020',
};

export type GateDetailProps = {
  gate: Gate | null;
  approverId: string;
  onUpdated: (gate: Gate) => void;
};

export function GateDetail({ gate, approverId, onUpdated }: GateDetailProps) {
  if (!gate) {
    return (
      <div style={{ color: colors.textMuted, padding: 24 }}>
        Select a pending gate from the queue.
      </div>
    );
  }

  const q = quorumProgress(gate);
  const managerBanner = gate.escalation_target === 'manager';

  return (
    <article
      style={{
        background: colors.bgCard,
        border: `1px solid ${colors.border}`,
        borderRadius: 12,
        padding: 20,
      }}
    >
      {managerBanner ? (
        <div
          role="status"
          style={{
            background: 'rgba(255, 176, 32, 0.12)',
            border: `1px solid ${colors.warn}`,
            color: colors.warn,
            padding: '10px 14px',
            borderRadius: 8,
            marginBottom: 16,
            fontSize: 14,
          }}
        >
          Escalation target: <strong>manager</strong> (empty approver roster — do not invent
          approvers).
        </div>
      ) : null}

      <header style={{ marginBottom: 16 }}>
        <h2 style={{ margin: '0 0 4px', color: colors.accent }}>{gate.condition}</h2>
        <div style={{ color: colors.textMuted, fontSize: 13 }}>
          {gate.project_id}
          {gate.task_id ? ` · ${gate.task_id}` : ''} · status={gate.status}
        </div>
        <div style={{ marginTop: 8, fontSize: 14 }}>
          Quorum progress:{' '}
          <strong style={{ color: colors.text }}>
            {q.have} / {q.need}
          </strong>
          <span
            style={{
              display: 'inline-block',
              marginLeft: 10,
              width: 120,
              height: 6,
              background: colors.bgElevated,
              borderRadius: 4,
              verticalAlign: 'middle',
              overflow: 'hidden',
            }}
          >
            <span
              style={{
                display: 'block',
                height: '100%',
                width: `${Math.min(100, (q.have / Math.max(1, q.need)) * 100)}%`,
                background: colors.accent,
              }}
            />
          </span>
        </div>
      </header>

      <section style={{ marginBottom: 16 }}>
        <h3 style={{ fontSize: 14, color: colors.textMuted, margin: '0 0 6px' }}>Evidence</h3>
        <p style={{ margin: 0 }}>{gate.evidence?.summary || '—'}</p>
      </section>

      {(gate.approvals?.length || 0) > 0 ? (
        <section style={{ marginBottom: 16 }}>
          <h3 style={{ fontSize: 14, color: colors.textMuted, margin: '0 0 6px' }}>Approvals</h3>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {gate.approvals.map((a, i) => (
              <li key={`${a.approver_id}-${i}`}>
                {a.approver_id}
                {a.comment ? ` — ${a.comment}` : ''}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {(gate.more_info_requests?.length || 0) > 0 ? (
        <section style={{ marginBottom: 16 }}>
          <h3 style={{ fontSize: 14, color: colors.textMuted, margin: '0 0 6px' }}>
            More-info requests
          </h3>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {gate.more_info_requests!.map((a, i) => (
              <li key={`${a.approver_id}-mi-${i}`}>
                {a.approver_id}: {a.comment}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <GateActions gate={gate} approverId={approverId} onUpdated={onUpdated} />
    </article>
  );
}

export default GateDetail;
