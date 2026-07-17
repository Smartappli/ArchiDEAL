import { useCallback, useEffect, useState } from "react";
import type { ModuleRuntimeConfig } from "../config/moduleRegistry";
import { fetchModuleConnection } from "../lib/moduleApi";
import type { ModuleConnection, ModuleKey } from "../types";

type ModuleConnectionMap = Partial<Record<ModuleKey, ModuleConnection>>;

export function useModuleConnections(runtimes: Record<ModuleKey, ModuleRuntimeConfig>, intervalMs = 30_000) {
  const [connections, setConnections] = useState<ModuleConnectionMap>({});
  const [isRefreshing, setIsRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    setIsRefreshing(true);

    try {
      const entries = await Promise.all(
        Object.values(runtimes).map(async (runtime) => {
          const connection = await fetchModuleConnection(runtime);

          return [runtime.key, connection] as const;
        }),
      );

      setConnections(Object.fromEntries(entries) as ModuleConnectionMap);
    } finally {
      setIsRefreshing(false);
    }
  }, [runtimes]);

  useEffect(() => {
    void refresh();

    const interval = window.setInterval(() => {
      void refresh();
    }, intervalMs);

    return () => window.clearInterval(interval);
  }, [intervalMs, refresh]);

  return {
    connections,
    isRefreshing,
    refresh,
  };
}
