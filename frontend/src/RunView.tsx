import { useRef, useState } from 'react';
import { api } from './api';

interface Line {
  type: 'stdout' | 'stderr' | 'exit';
  text?: string;
  code?: number;
}

export default function RunView() {
  const [command, setCommand] = useState('python --version');
  const [cwd, setCwd] = useState('');
  const [log, setLog] = useState<Line[]>([]);
  const [running, setRunning] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  async function run() {
    if (!command.trim() || running) return;
    setLog([]);
    setRunning(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      await api.run(
        command,
        cwd,
        (ev) => setLog((prev) => [...prev, ev]),
        ctrl.signal,
      );
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setLog((prev) => [...prev, { type: 'stderr', text: String((e as Error).message || e) }]);
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }

  return (
    <div className="run-layout">
      <div className="run-controls">
        <input
          className="cmd-input"
          value={command}
          placeholder="command"
          onChange={(e) => setCommand(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void run();
          }}
        />
        <input
          className="cwd-input"
          value={cwd}
          placeholder="cwd (workspace-relative)"
          onChange={(e) => setCwd(e.target.value)}
        />
        {running ? (
          <button className="btn danger" onClick={() => abortRef.current?.abort()}>
            Stop
          </button>
        ) : (
          <button className="btn primary" onClick={() => void run()}>
            Run
          </button>
        )}
      </div>
      <pre className="run-log">
        {log.map((l, i) => (
          <span key={i} className={l.type === 'stderr' ? 'run-err' : l.type === 'exit' ? 'run-exit' : ''}>
            {l.type === 'exit' ? `\n[exit ${l.code}]\n` : l.text}
          </span>
        ))}
      </pre>
    </div>
  );
}
