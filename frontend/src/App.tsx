import { useEffect, useState } from 'react';
import type { ApiKeys, Meta } from './types';
import { api, getApiKeys, setApiKeys } from './api';
import { on } from './state';
import ChatView from './ChatView';
import BoardView from './BoardView';
import FilesView from './FilesView';
import RunView from './RunView';
import DataView from './DataView';

type View = 'chat' | 'board' | 'files' | 'run' | 'data';

export default function App() {
  const [view, setView] = useState<View>('chat');
  const [meta, setMeta] = useState<Meta | null>(null);
  const [theme, setTheme] = useState<'light' | 'dark'>(
    () => (localStorage.getItem('studio-theme') as 'light' | 'dark') || 'dark',
  );
  const [keysOpen, setKeysOpen] = useState(false);

  useEffect(() => {
    api.meta().then(setMeta).catch(() => {});
  }, []);

  useEffect(
    () =>
      on('navigate', (e) => {
        const v = (e as CustomEvent).detail as View;
        if (v) setView(v);
      }),
    [],
  );

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('studio-theme', theme);
  }, [theme]);

  const tabs: { id: View; label: string }[] = [
    { id: 'chat', label: 'Chat' },
    { id: 'board', label: 'Board' },
    { id: 'files', label: 'Files' },
    { id: 'run', label: 'Run' },
    { id: 'data', label: 'Data' },
  ];

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">⚡ Agent Studio</div>
        <nav className="tabs">
          {tabs.map((t) => (
            <button
              key={t.id}
              className={view === t.id ? 'tab active' : 'tab'}
              onClick={() => setView(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <div className="topbar-right">
          <button
            className="icon-btn"
            title="Toggle theme"
            onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
          <button className="avatar" title="API keys" onClick={() => setKeysOpen(true)}>
            ⚙️
          </button>
        </div>
      </header>

      <main className="main">
        {view === 'chat' && <ChatView meta={meta} />}
        {view === 'board' && <BoardView />}
        {view === 'files' && <FilesView />}
        {view === 'run' && <RunView />}
        {view === 'data' && <DataView />}
      </main>

      {keysOpen && <ApiKeysModal meta={meta} onClose={() => setKeysOpen(false)} />}
    </div>
  );
}

function ApiKeysModal({ meta, onClose }: { meta: Meta | null; onClose: () => void }) {
  const [keys, setKeys] = useState<ApiKeys>(getApiKeys());

  const save = () => {
    setApiKeys(keys);
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>API keys</h2>
        <p className="muted">
          Keys are stored in your browser only and sent per-request. The server never persists them.
        </p>
        <div className="key-list">
          {(meta?.providers ?? []).map((p) => (
            <div className="key-row" key={p.id}>
              <label>
                {p.name}
                {p.hasKey ? <span className="tag">env</span> : null}
              </label>
              <input
                type="password"
                placeholder={p.hasKey ? '•••••• (server env)' : p.envKey}
                value={keys[p.envKey] || ''}
                onChange={(e) => setKeys({ ...keys, [p.envKey]: e.target.value })}
              />
            </div>
          ))}
          <div className="key-row">
            <label>Tavily (web search)</label>
            <input
              type="password"
              placeholder="TAVILY_API_KEY"
              value={keys['TAVILY_API_KEY'] || ''}
              onChange={(e) => setKeys({ ...keys, TAVILY_API_KEY: e.target.value })}
            />
          </div>
        </div>
        <div className="modal-actions">
          <button className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" onClick={save}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
