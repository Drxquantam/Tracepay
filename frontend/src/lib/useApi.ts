// A small data-loading hook: fetch on mount, optional polling, manual reload.
// Deliberately tiny instead of pulling in a data-fetching library.

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";

type PollEvery<T> = number | ((data: T) => number | null) | undefined;

export function useApi<T>(path: string | null, pollEvery?: PollEvery<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(path !== null);
  // Keep the latest poll rule in a ref, so changing it doesn't restart the effect.
  const pollRef = useRef(pollEvery);
  pollRef.current = pollEvery;

  const load = useCallback(async () => {
    if (!path) return null;
    try {
      const result = await api<T>(path);
      setData(result);
      setError(null);
      return result;
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
      return null;
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    const tick = async () => {
      const result = await load();
      if (cancelled) return;
      const rule = pollRef.current;
      const delay = typeof rule === "function" ? (result ? rule(result) : 5000) : rule;
      if (delay) timer = setTimeout(tick, delay);
    };
    setLoading(path !== null);
    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [load, path]);

  return { data, error, loading, reload: load };
}
