"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Result<T> = { key: string; data?: T; error?: string };

export function useApi<T>(path: string | null) {
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<Result<T>>();
  const key = JSON.stringify([path, revision]);
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    api<T>(path, { signal: controller.signal }).then(
      (data) => { if (!controller.signal.aborted) setResult({ key, data }); },
      (error: Error) => { if (!controller.signal.aborted) setResult({ key, error: error.message }); },
    );
    return () => controller.abort();
  }, [key, path]);

  const current = result?.key === key ? result : undefined;
  return {
    data: current?.data, error: current?.error,
    loading: Boolean(path && !current),
    refresh: () => setRevision((value) => value + 1),
  };
}
