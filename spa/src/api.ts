/** Humangate HTTP client for Approvals SPA */

export type GateApproval = {
  approver_id: string;
  comment?: string | null;
  at: string;
};

export type Gate = {
  id: string;
  gate_id?: string;
  status: 'pending' | 'approved' | 'rejected' | 'escalated' | string;
  condition: string;
  project_id: string;
  task_id?: string | null;
  required_approvals: number;
  approvals: GateApproval[];
  rejections: GateApproval[];
  more_info_requests?: GateApproval[];
  escalation_target?: string | null;
  evidence?: { summary?: string; artifact_paths?: string[] };
  resolve_reason?: string | null;
  opened_at?: string;
  created_at?: string;
  updated_at?: string;
  resume_payload?: Record<string, unknown> | null;
};

export type GatesList = {
  pending: Gate[];
  approved: Gate[];
  rejected: Gate[];
  escalated: Gate[];
  pending_count?: number;
  max_pending?: number;
};

const BASE =
  (typeof import.meta !== 'undefined' &&
    (import.meta as ImportMeta & { env?: { VITE_HUMANGATE_BASE?: string } }).env
      ?.VITE_HUMANGATE_BASE) ||
  '/humangate';

async function req<T>(
  method: string,
  path: string,
  body?: Record<string, unknown>
): Promise<{ status: number; data: T }> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'content-type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = (await res.json().catch(() => ({}))) as T;
  return { status: res.status, data };
}

export async function listGates(): Promise<GatesList> {
  const { status, data } = await req<GatesList>('GET', '/gates');
  if (status >= 400) throw new Error((data as { error?: string }).error || `list failed ${status}`);
  return data;
}

export async function getGate(id: string): Promise<Gate> {
  const { status, data } = await req<Gate>('GET', `/gates/${id}`);
  if (status >= 400) throw new Error((data as { error?: string }).error || `get failed ${status}`);
  return data;
}

export async function approveGate(
  id: string,
  payload: { approver_id: string; comment?: string }
): Promise<Gate> {
  const { status, data } = await req<Gate & { error?: string }>('POST', `/gates/${id}/approve`, payload);
  if (status >= 400) throw new Error(data.error || `approve failed ${status}`);
  return data;
}

export async function rejectGate(
  id: string,
  payload: { approver_id: string; comment: string }
): Promise<Gate> {
  if (!payload.comment?.trim()) throw new Error('Reject rationale (comment) is required');
  const { status, data } = await req<Gate & { error?: string }>('POST', `/gates/${id}/reject`, payload);
  if (status >= 400) throw new Error(data.error || `reject failed ${status}`);
  return data;
}

export async function requestMoreInfo(
  id: string,
  payload: { approver_id: string; comment: string }
): Promise<Gate> {
  if (!payload.comment?.trim()) throw new Error('More-info comment is required');
  const { status, data } = await req<Gate & { error?: string }>(
    'POST',
    `/gates/${id}/more-info`,
    payload
  );
  if (status >= 400) throw new Error(data.error || `more-info failed ${status}`);
  return data;
}

export function quorumProgress(gate: Gate): { have: number; need: number; label: string } {
  const have = gate.approvals?.length || 0;
  const need = gate.required_approvals || 1;
  return { have, need, label: `${have} / ${need}` };
}
