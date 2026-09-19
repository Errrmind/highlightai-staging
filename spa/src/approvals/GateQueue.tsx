import React from 'react';
import type { Gate } from '../api';
import { quorumProgress } from '../api';

const colors = {
  bgCard: '#1a2236',
  border: '#2a3548',
  text: '#f4f6fb',
  textMuted: '#a8b3c7',
  accent: '#7c5cff',
};

export type GateQueueProps = {
  gates: Gate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
};

export function GateQueue({ gates, selectedId, onSelect }: GateQueueProps) {
  if (!gates.length) {
    return <p style={{ color: colors.textMuted, padding: 16 }}>No pending gates.</p>;
  }
  return (
    <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
      {gates.map((g) => {
        const q = quorumProgress(g);
        const selected = g.id === selectedId;
        return (
          <li key={g.id}>
            <button
              type="button"
              onClick={() => onSelect(g.id)}
              style={{
                width: '100%',
                textAlign: 'left',
                padding: '12px 14px',
                marginBottom: 8,
                background: selected ? '#141a28' : colors.bgCard,
                border: `1px solid ${selected ? colors.accent : colors.border}`,
                borderRadius: 8,
                color: colors.text,
                cursor: 'pointer',
              }}
            >
              <div style={{ fontWeight: 600, color: colors.accent }}>{g.condition}</div>
              <div style={{ fontSize: 13, color: colors.textMuted }}>{g.project_id}</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>
                Quorum {q.label}
                {g.escalation_target === 'manager' ? ' · manager' : ''}
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export default GateQueue;
