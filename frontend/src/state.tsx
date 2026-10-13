import { useEffect, useState } from 'react';

// A tiny global event bus for cross-view notifications (e.g. chat updates a project).
export const bus = new EventTarget();

export function emit(type: string, detail?: unknown): void {
  bus.dispatchEvent(new CustomEvent(type, { detail }));
}

export function on(type: string, fn: (e: Event) => void): () => void {
  bus.addEventListener(type, fn);
  return () => bus.removeEventListener(type, fn);
}

// Re-render a component when a bus event fires, returning the last detail.
export function useBusEvent<T = unknown>(type: string): T | undefined {
  const [detail, setDetail] = useState<T | undefined>(undefined);
  useEffect(() => {
    const handler = (e: Event) => setDetail((e as CustomEvent).detail as T);
    bus.addEventListener(type, handler);
    return () => bus.removeEventListener(type, handler);
  }, [type]);
  return detail;
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): {
  data: T | null;
  error: string | null;
  reload: () => void;
} {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    setError(null);
    fn()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(String(e?.message || e)));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { data, error, reload: () => setTick((t) => t + 1) };
}

export function uid(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}
