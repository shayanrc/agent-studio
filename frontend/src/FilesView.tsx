import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { FileInfo, TreeNode } from './types';
import { api } from './api';
import { on } from './state';

export default function FilesView() {
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [file, setFile] = useState<FileInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    api.tree('').then(setTree).catch((e) => setError(String(e.message || e)));
  }, [tick]);

  useEffect(
    () =>
      on('workspace-changed', () => {
        setTick((t) => t + 1);
        if (file) {
          api.file(file.path).then(setFile).catch(() => {});
        }
      }),
    [file],
  );

  async function open(path: string) {
    try {
      setFile(await api.file(path));
      setError(null);
    } catch (e) {
      setError(String((e as Error).message || e));
    }
  }

  return (
    <div className="files-layout">
      <aside className="sidebar">
        <div className="sidebar-head">
          <span>Workspace</span>
          <button className="icon-btn" onClick={() => setTick((t) => t + 1)}>↻</button>
        </div>
        {tree && <TreeNodes nodes={tree.children ?? []} onOpen={open} />}
      </aside>
      <div className="file-main">
        {error && <div className="error-banner">⚠ {error}</div>}
        {file ? (
          <>
            <div className="file-head">
              <code>{file.path}</code>
              <span className="muted">{file.size} bytes</span>
            </div>
            {file.path.endsWith('.md') ? (
              <div className="md file-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{file.content}</ReactMarkdown>
              </div>
            ) : (
              <pre className="file-content">{file.content}</pre>
            )}
          </>
        ) : (
          <div className="empty">Select a file to view it.</div>
        )}
      </div>
    </div>
  );
}

function TreeNodes({ nodes, onOpen }: { nodes: TreeNode[]; onOpen: (path: string) => void }) {
  return (
    <ul className="tree">
      {nodes.map((n) => (
        <li key={n.path}>
          {n.type === 'dir' ? (
            <details>
              <summary>📁 {n.name}</summary>
              <TreeNodes nodes={n.children ?? []} onOpen={onOpen} />
            </details>
          ) : (
            <span className="file-node" onClick={() => onOpen(n.path)}>
              📄 {n.name}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
