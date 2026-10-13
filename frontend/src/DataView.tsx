import { useEffect, useState } from 'react';
import type { TreeNode } from './types';
import { api } from './api';
import { on } from './state';

type Row = Record<string, string | number>;

function parseCSV(text: string): Row[] {
  const rows = text.split(/\r?\n/).filter((l) => l.trim());
  if (!rows.length) return [];
  const parseLine = (l: string): string[] => {
    const out: string[] = [];
    let cur = '';
    let inQ = false;
    for (let i = 0; i < l.length; i++) {
      const c = l[i];
      if (inQ) {
        if (c === '"') {
          if (l[i + 1] === '"') {
            cur += '"';
            i++;
          } else inQ = false;
        } else cur += c;
      } else if (c === '"') inQ = true;
      else if (c === ',') {
        out.push(cur);
        cur = '';
      } else cur += c;
    }
    out.push(cur);
    return out;
  };
  const header = parseLine(rows[0]);
  return rows.slice(1).map((r) => {
    const vals = parseLine(r);
    const obj: Row = {};
    header.forEach((h, i) => {
      const v = vals[i] ?? '';
      obj[h.trim()] = v.trim() !== '' && !isNaN(Number(v)) ? Number(v) : v;
    });
    return obj;
  });
}

function toRows(data: unknown): Row[] {
  if (Array.isArray(data)) return data.map((x) => (typeof x === 'object' ? (x as Row) : { value: x as string | number }));
  if (data && typeof data === 'object') return [data as Row];
  return [];
}

export default function DataView() {
  const [path, setPath] = useState('demo-app/data.csv');
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [xCol, setXCol] = useState('');
  const [yCol, setYCol] = useState('');
  const [chartType, setChartType] = useState<'bar' | 'line'>('bar');

  useEffect(() => {
    api.tree('').then(setTree).catch(() => {});
  }, []);
  useEffect(() => on('workspace-changed', () => api.tree('').then(setTree).catch(() => {})), []);

  const dataFiles = collectDataFiles(tree);

  async function load(p = path) {
    setError(null);
    try {
      const f = await api.file(p);
      const raw = f.content;
      let data: unknown;
      if (p.endsWith('.csv')) {
        setRows(parseCSV(raw));
      } else {
        try {
          data = JSON.parse(raw);
        } catch {
          setError('Could not parse JSON.');
          return;
        }
        setRows(toRows(data));
      }
    } catch (e) {
      setError(String((e as Error).message || e));
      setRows(null);
    }
  }

  useEffect(() => {
    if (rows) return;
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns = rows && rows.length ? Object.keys(rows[0]) : [];
  const numericCols = columns.filter((c) => rows?.some((r) => typeof r[c] === 'number'));
  const effectiveY = yCol || numericCols[0] || columns[1] || '';
  const effectiveX = xCol || columns[0] || '';

  return (
    <div className="data-layout">
      <div className="data-controls">
        <input
          list="data-files"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void load()}
        />
        <datalist id="data-files">
          {dataFiles.map((f) => (
            <option key={f} value={f} />
          ))}
        </datalist>
        <button className="btn primary" onClick={() => void load()}>Load</button>
      </div>

      {error && <div className="error-banner">⚠ {error}</div>}

      {rows && rows.length > 0 && (
        <>
          <div className="chart-controls">
            <label>
              X
              <select value={effectiveX} onChange={(e) => setXCol(e.target.value)}>
                {columns.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </label>
            <label>
              Y
              <select value={effectiveY} onChange={(e) => setYCol(e.target.value)}>
                {numericCols.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </label>
            <label>
              Type
              <select value={chartType} onChange={(e) => setChartType(e.target.value as 'bar' | 'line')}>
                <option value="bar">Bar</option>
                <option value="line">Line</option>
              </select>
            </label>
          </div>
          {numericCols.includes(effectiveY) && (
            <Chart
              labels={rows.map((r) => String(r[effectiveX]))}
              values={rows.map((r) => Number(r[effectiveY]))}
              type={chartType}
            />
          )}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {columns.map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    {columns.map((c) => (
                      <td key={c}>{String(r[c])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function collectDataFiles(node: TreeNode | null): string[] {
  const out: string[] = [];
  const walk = (n: TreeNode) => {
    if (n.type === 'file' && (n.name.endsWith('.csv') || n.name.endsWith('.json'))) out.push(n.path);
    n.children?.forEach(walk);
  };
  if (node) walk(node);
  return out;
}

function Chart({
  labels,
  values,
  type,
}: {
  labels: string[];
  values: number[];
  type: 'bar' | 'line';
}) {
  const w = 720;
  const h = 260;
  const pad = 30;
  const max = Math.max(1, ...values);
  const n = values.length;
  const innerW = w - pad * 2;
  const innerH = h - pad * 2;
  const x = (i: number) => pad + (n <= 1 ? innerW / 2 : (innerW * i) / (n - 1));
  const y = (v: number) => pad + innerH - (innerH * v) / max;
  const barW = Math.min(40, innerW / Math.max(1, n) / 2);

  const linePath =
    type === 'line'
      ? values.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(v)}`).join(' ')
      : '';

  return (
    <svg className="chart" viewBox={`0 0 ${w} ${h}`}>
      <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} className="axis" />
      <line x1={pad} y1={pad} x2={pad} y2={h - pad} className="axis" />
      {values.map((v, i) => (
        <g key={i}>
          {type === 'bar' ? (
            <rect x={x(i) - barW / 2} y={y(v)} width={barW} height={h - pad - y(v)} className="bar" />
          ) : (
            <circle cx={x(i)} cy={y(v)} r={3} className="dot" />
          )}
          <text x={x(i)} y={h - pad + 14} className="axis-label" textAnchor="middle">
            {labels[i]}
          </text>
        </g>
      ))}
      {type === 'line' && linePath && <path d={linePath} className="line" />}
    </svg>
  );
}
