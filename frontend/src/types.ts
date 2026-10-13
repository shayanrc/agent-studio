export type ToolKind = 'web' | 'code' | 'mcp' | 'skill' | 'tool' | 'file' | 'run';

export interface ToolEvent {
  kind: ToolKind;
  label: string;
  detail: string;
  path?: string;
  action?: 'create' | 'edit' | 'delete';
  diff?: string;
  changeId?: string;
  applied?: boolean;
  exitCode?: number;
  stdout?: string;
  stderr?: string;
}

export interface Msg {
  id: string;
  role: 'user' | 'assistant';
  kind: 'message' | 'summary';
  content: string;
  toolEvents?: ToolEvent[];
  summaryOf?: Msg[];
  freedTokens?: number;
  createdAt: number;
}

export interface Branch {
  id: string;
  name: string;
  forkOf?: { branchId: string; messageId: string | null } | null;
  messages: Msg[];
  createdAt: number;
}

export interface Conversation {
  id: string;
  title: string;
  branches: Branch[];
  activeBranchId: string;
  createdAt: number;
  updatedAt: number;
}

export interface ConversationSummary {
  id: string;
  title: string;
  branchCount: number;
  updatedAt: number;
}

export interface ModelInfo {
  id: string;
  name: string;
  contextWindow: number;
}

export interface ProviderInfo {
  id: string;
  name: string;
  envKey: string;
  hasKey: boolean;
  models: ModelInfo[];
  unavailableReason?: string;
}

export interface CapabilityInfo {
  id: string;
  name: string;
  kind: string;
  available: boolean;
  envKey: string | null;
  tokens: number;
}

export interface Meta {
  providers: ProviderInfo[];
  capabilities: CapabilityInfo[];
  systemPromptTokens: number;
}

export interface Spec {
  title: string;
  goal: string;
  requirements: string[];
  constraints: string[];
  assumptions: string[];
  updatedAt: number;
}

export interface Phase {
  id: string;
  name: string;
  goal: string;
}

export interface Plan {
  overview: string;
  phases: Phase[];
  updatedAt: number;
}

export type TaskStatus = 'pending' | 'in-progress' | 'done' | 'blocked';

export interface Task {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  phase?: string | null;
  acceptance: string[];
  dependsOn: string[];
  result?: string | null;
  createdAt: number;
  updatedAt: number;
}

export interface Project {
  id: string;
  name: string;
  root: string;
  spec: Spec;
  plan: Plan;
  tasks: Task[];
  createdAt: number;
  updatedAt: number;
}

export type ApiKeys = Record<string, string>;

export type ChatEvent =
  | { type: 'user'; message: Msg }
  | { type: 'delta'; text: string }
  | { type: 'tool'; event: ToolEvent }
  | { type: 'done'; conversation: Conversation }
  | { type: 'project'; project: Project }
  | { type: 'error'; message: string };

export interface TreeNode {
  name: string;
  path: string;
  type: 'dir' | 'file';
  size?: number;
  children?: TreeNode[];
}

export interface FileInfo {
  path: string;
  content: string;
  size: number;
}
