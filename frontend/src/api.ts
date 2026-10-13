import type {
  ApiKeys,
  ChatEvent,
  Conversation,
  ConversationSummary,
  FileInfo,
  Meta,
  Phase,
  Project,
  Spec,
  Task,
  TreeNode,
} from './types';

const BASE = '';

// --- API keys (browser localStorage only, never persisted server-side) ---

export function getApiKeys(): ApiKeys {
  try {
    return JSON.parse(localStorage.getItem('studio-api-keys') || '{}');
  } catch {
    return {};
  }
}

export function setApiKeys(keys: ApiKeys): void {
  localStorage.setItem('studio-api-keys', JSON.stringify(keys));
}

// --- helpers ---

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { error?: string }).error || res.statusText);
  }
  return res.json() as Promise<T>;
}

function post(url: string, body: unknown): Promise<Response> {
  return fetch(`${BASE}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/** Stream a NDJSON response line-by-line, invoking onEvent per parsed object. */
export async function streamNDJSON(
  url: string,
  body: unknown,
  onEvent: (ev: Record<string, unknown>) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${BASE}${url}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => '');
    throw new Error(text || res.statusText);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 1);
      if (!line) continue;
      try {
        onEvent(JSON.parse(line));
      } catch {
        /* ignore malformed line */
      }
    }
  }
  const tail = buffer.trim();
  if (tail) {
    try {
      onEvent(JSON.parse(tail));
    } catch {
      /* ignore */
    }
  }
}

// --- API surface ---

export const api = {
  meta: (): Promise<Meta> => fetch(`${BASE}/api/meta`).then((r) => j<Meta>(r)),

  // conversations
  listConversations: (): Promise<ConversationSummary[]> =>
    fetch(`${BASE}/api/conversations`).then((r) => j<ConversationSummary[]>(r)),
  createConversation: (): Promise<Conversation> =>
    post('/api/conversations', {}).then((r) => j<Conversation>(r)),
  getConversation: (id: string): Promise<Conversation> =>
    fetch(`${BASE}/api/conversations/${id}`).then((r) => j<Conversation>(r)),
  renameConversation: (id: string, title: string): Promise<Conversation> =>
    fetch(`${BASE}/api/conversations/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    }).then((r) => j<Conversation>(r)),
  deleteConversation: (id: string): Promise<unknown> =>
    fetch(`${BASE}/api/conversations/${id}`, { method: 'DELETE' }).then((r) => j(r)),
  activate: (id: string, branchId: string): Promise<Conversation> =>
    post(`/api/conversations/${id}/activate`, { branchId }).then((r) => j<Conversation>(r)),
  branch: (
    id: string,
    branchId: string,
    messageId: string | null,
    name?: string,
  ): Promise<Conversation> =>
    post(`/api/conversations/${id}/branch`, { branchId, messageId, name }).then((r) =>
      j<Conversation>(r),
    ),
  rewind: (id: string, branchId: string, messageId: string): Promise<Conversation> =>
    post(`/api/conversations/${id}/rewind`, { branchId, messageId }).then((r) =>
      j<Conversation>(r),
    ),
  combine: (id: string, sourceBranchId: string, targetBranchId: string): Promise<Conversation> =>
    post(`/api/conversations/${id}/combine`, { sourceBranchId, targetBranchId }).then((r) =>
      j<Conversation>(r),
    ),
  summarize: (
    id: string,
    branchId: string,
    fromId: string,
    toId: string,
    provider: string,
    model: string,
    keys: ApiKeys,
  ): Promise<Conversation> =>
    post(`/api/conversations/${id}/summarize`, {
      branchId,
      fromId,
      toId,
      provider,
      model,
      apiKeys: keys,
    }).then((r) => j<Conversation>(r)),

  // chat (streaming)
  chat: (
    id: string,
    body: Record<string, unknown>,
    onEvent: (ev: ChatEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> => streamNDJSON(`/api/conversations/${id}/chat`, body, (ev) => onEvent(ev as ChatEvent), signal),

  // projects
  listProjects: (): Promise<Project[]> =>
    fetch(`${BASE}/api/projects`).then((r) => j<Project[]>(r)),
  createProject: (name: string, root: string): Promise<Project> =>
    post('/api/projects', { name, root }).then((r) => j<Project>(r)),
  getProject: (id: string): Promise<Project> =>
    fetch(`${BASE}/api/projects/${id}`).then((r) => j<Project>(r)),
  renameProject: (id: string, name: string): Promise<Project> =>
    fetch(`${BASE}/api/projects/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }).then((r) => j<Project>(r)),
  deleteProject: (id: string): Promise<unknown> =>
    fetch(`${BASE}/api/projects/${id}`, { method: 'DELETE' }).then((r) => j(r)),
  putSpec: (id: string, spec: Partial<Spec>): Promise<Project> =>
    fetch(`${BASE}/api/projects/${id}/spec`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(spec),
    }).then((r) => j<Project>(r)),
  putPlan: (id: string, plan: { overview: string; phases: Phase[] }): Promise<Project> =>
    fetch(`${BASE}/api/projects/${id}/plan`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(plan),
    }).then((r) => j<Project>(r)),
  putTasks: (id: string, tasks: Task[]): Promise<Project> =>
    fetch(`${BASE}/api/projects/${id}/tasks`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tasks }),
    }).then((r) => j<Project>(r)),
  patchTask: (id: string, taskId: string, patch: Partial<Task>): Promise<Project> =>
    fetch(`${BASE}/api/projects/${id}/tasks/${taskId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    }).then((r) => j<Project>(r)),
  generateDocs: (id: string): Promise<Project> =>
    post(`/api/projects/${id}/docs`, {}).then((r) => j<Project>(r)),

  // workspace
  tree: (path = ''): Promise<TreeNode> =>
    fetch(`${BASE}/api/workspace/tree?path=${encodeURIComponent(path)}`)
      .then((r) => j<{ tree: TreeNode }>(r))
      .then((d) => d.tree),
  file: (path: string): Promise<FileInfo> =>
    fetch(`${BASE}/api/workspace/file?path=${encodeURIComponent(path)}`).then((r) => j<FileInfo>(r)),

  // changes
  applyChanges: (changeIds: string[]): Promise<{ applied: string[] }> =>
    post('/api/changes/apply', { changeIds }).then((r) => j(r)),
  discardChanges: (changeIds: string[]): Promise<unknown> =>
    post('/api/changes/discard', { changeIds }).then((r) => j(r)),

  // command runner (streaming)
  run: (
    command: string,
    cwd: string,
    onEvent: (ev: { type: 'stdout' | 'stderr' | 'exit'; text?: string; code?: number }) => void,
    signal?: AbortSignal,
  ): Promise<void> => streamNDJSON('/api/run', { command, cwd }, (ev) => onEvent(ev as never), signal),
};
