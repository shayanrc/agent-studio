import { useCallback, useEffect, useState } from 'react';
import type { Phase, Project, Spec, Task, TaskStatus } from './types';
import { api } from './api';
import { bus, on, uid } from './state';

const STATUSES: TaskStatus[] = ['pending', 'in-progress', 'done', 'blocked'];

function lines(s: string): string[] {
  return s.split('\n').map((x) => x.trim()).filter(Boolean);
}

export default function BoardView() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Project | null>(null);

  const reload = useCallback(
    async (keepId?: string) => {
      const list = await api.listProjects();
      setProjects(list);
      const id = keepId ?? selected?.id ?? list[0]?.id;
      if (id) setSelected(list.find((p) => p.id === id) ?? list[0] ?? null);
    },
    [selected?.id],
  );

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(
    () =>
      on('project-updated', (e) => {
        const p = (e as CustomEvent).detail as Project;
        setProjects((prev) => prev.map((x) => (x.id === p.id ? p : x)));
        setSelected((prev) => (prev && prev.id === p.id ? p : prev));
      }),
    [],
  );

  return (
    <div className="board-layout">
      <aside className="sidebar">
        <div className="sidebar-head">
          <span>Projects</span>
          <button
            className="icon-btn"
            title="New project"
            onClick={async () => {
              const p = await api.createProject(`Project ${projects.length + 1}`, `project-${projects.length + 1}`);
              await reload(p.id);
            }}
          >
            ＋
          </button>
        </div>
        {projects.map((p) => (
          <div
            key={p.id}
            className={selected?.id === p.id ? 'conv-item active' : 'conv-item'}
            onClick={() => setSelected(p)}
          >
            <span className="conv-title">{p.name}</span>
            <button
              className="icon-btn"
              title="Delete"
              onClick={async (e) => {
                e.stopPropagation();
                await api.deleteProject(p.id);
                if (selected?.id === p.id) setSelected(null);
                await reload();
              }}
            >
              🗑
            </button>
          </div>
        ))}
      </aside>

      <div className="board-main">
        {selected ? (
          <Editor key={selected.id} project={selected} onSaved={reload} />
        ) : (
          <div className="empty">Select or create a project to plan work.</div>
        )}
      </div>
    </div>
  );
}

function Editor({ project, onSaved }: { project: Project; onSaved: () => Promise<void> }) {
  const [name, setName] = useState(project.name);
  const [spec, setSpec] = useState<Spec>(project.spec);
  const [overview, setOverview] = useState(project.plan.overview);
  const [phases, setPhases] = useState<Phase[]>(project.plan.phases);
  const [tasks, setTasks] = useState<Task[]>(project.tasks);

  async function saveSpec() {
    const p = await api.putSpec(project.id, spec);
    bus.dispatchEvent(new CustomEvent('project-updated', { detail: p }));
    await onSaved();
  }
  async function savePlan() {
    const p = await api.putPlan(project.id, { overview, phases });
    bus.dispatchEvent(new CustomEvent('project-updated', { detail: p }));
    await onSaved();
  }
  async function saveTasks() {
    const p = await api.putTasks(project.id, tasks);
    bus.dispatchEvent(new CustomEvent('project-updated', { detail: p }));
    await onSaved();
  }

  async function rename() {
    if (name !== project.name) {
      const p = await api.renameProject(project.id, name);
      bus.dispatchEvent(new CustomEvent('project-updated', { detail: p }));
      await onSaved();
    }
  }

  async function setStatus(t: Task, status: TaskStatus) {
    setTasks((prev) => prev.map((x) => (x.id === t.id ? { ...x, status } : x)));
    const p = await api.patchTask(project.id, t.id, { status });
    bus.dispatchEvent(new CustomEvent('project-updated', { detail: p }));
  }

  function implement(t: Task) {
    bus.dispatchEvent(new CustomEvent('navigate', { detail: 'chat' }));
    setTimeout(() => {
      bus.dispatchEvent(
        new CustomEvent('chat-request', {
          detail: {
            prompt: `Implement the task "${t.title}" for the ${project.name} project.`,
            projectId: project.id,
            taskId: t.id,
            label: `${project.name} › ${t.title}`,
          },
        }),
      );
    }, 50);
  }

  return (
    <div className="editor">
      <div className="editor-head">
        <input
          className="title-input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => void rename()}
        />
        <span className="muted">root: {project.root}</span>
        <button className="btn ghost" onClick={() => void api.generateDocs(project.id).then(() => onSaved())}>
          Write docs
        </button>
      </div>

      <details open>
        <summary>Spec</summary>
        <div className="form-grid">
          <label>Title</label>
          <input value={spec.title} onChange={(e) => setSpec({ ...spec, title: e.target.value })} />
          <label>Goal</label>
          <textarea value={spec.goal} onChange={(e) => setSpec({ ...spec, goal: e.target.value })} />
          <label>Requirements (one per line)</label>
          <textarea
            value={spec.requirements.join('\n')}
            onChange={(e) => setSpec({ ...spec, requirements: lines(e.target.value) })}
          />
          <label>Constraints (one per line)</label>
          <textarea
            value={spec.constraints.join('\n')}
            onChange={(e) => setSpec({ ...spec, constraints: lines(e.target.value) })}
          />
          <label>Assumptions (one per line)</label>
          <textarea
            value={spec.assumptions.join('\n')}
            onChange={(e) => setSpec({ ...spec, assumptions: lines(e.target.value) })}
          />
        </div>
        <button className="btn primary" onClick={() => void saveSpec()}>Save spec</button>
      </details>

      <details open>
        <summary>Plan</summary>
        <div className="form-grid">
          <label>Overview</label>
          <textarea value={overview} onChange={(e) => setOverview(e.target.value)} />
        </div>
        {phases.map((ph, i) => (
          <div className="phase-row" key={ph.id}>
            <input
              value={ph.name}
              onChange={(e) => setPhases(phases.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))}
            />
            <input
              value={ph.goal}
              onChange={(e) => setPhases(phases.map((x, j) => (j === i ? { ...x, goal: e.target.value } : x)))}
            />
            <button
              className="icon-btn"
              onClick={() => setPhases(phases.filter((_, j) => j !== i))}
            >
              ×
            </button>
          </div>
        ))}
        <button
          className="btn ghost"
          onClick={() => setPhases([...phases, { id: uid(), name: 'Phase', goal: '' }])}
        >
          ＋ Phase
        </button>
        <button className="btn primary" onClick={() => void savePlan()}>Save plan</button>
      </details>

      <details open>
        <summary>Tasks</summary>
        <div className="task-list">
          {tasks.map((t) => (
            <div className={`task-card status-${t.status}`} key={t.id}>
              <div className="task-row">
                <select value={t.status} onChange={(e) => void setStatus(t, e.target.value as TaskStatus)}>
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <input
                  value={t.title}
                  onChange={(e) => setTasks(tasks.map((x) => (x.id === t.id ? { ...x, title: e.target.value } : x)))}
                />
                <select
                  value={t.phase ?? ''}
                  onChange={(e) =>
                    setTasks(tasks.map((x) => (x.id === t.id ? { ...x, phase: e.target.value || null } : x)))
                  }
                >
                  <option value="">(no phase)</option>
                  {phases.map((ph) => (
                    <option key={ph.id} value={ph.id}>{ph.name}</option>
                  ))}
                </select>
                <button className="btn small primary" onClick={() => implement(t)}>
                  ⚡ Implement
                </button>
                <button
                  className="icon-btn"
                  onClick={() => setTasks(tasks.filter((x) => x.id !== t.id))}
                >
                  ×
                </button>
              </div>
              <textarea
                className="task-desc"
                placeholder="Description"
                value={t.description}
                onChange={(e) =>
                  setTasks(tasks.map((x) => (x.id === t.id ? { ...x, description: e.target.value } : x)))
                }
              />
              <textarea
                className="task-desc"
                placeholder="Acceptance criteria (one per line)"
                value={t.acceptance.join('\n')}
                onChange={(e) =>
                  setTasks(tasks.map((x) => (x.id === t.id ? { ...x, acceptance: lines(e.target.value) } : x)))
                }
              />
              {t.result && <div className="task-result">Result: {t.result}</div>}
            </div>
          ))}
        </div>
        <button
          className="btn ghost"
          onClick={() =>
            setTasks([
              ...tasks,
              {
                id: uid(),
                title: 'New task',
                description: '',
                status: 'pending',
                phase: phases[0]?.id ?? null,
                acceptance: [],
                dependsOn: [],
                createdAt: Date.now(),
                updatedAt: Date.now(),
              },
            ])
          }
        >
          ＋ Task
        </button>
        <button className="btn primary" onClick={() => void saveTasks()}>Save tasks</button>
      </details>
    </div>
  );
}
