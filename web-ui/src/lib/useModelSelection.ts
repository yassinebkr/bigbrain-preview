/** Load configured models and apply selections through the runtime-aware API. */
import { useCallback, useEffect, useState } from 'react';

export interface ModelRole {
  key: string;
  display_name: string;
  runtime?: { component: string; registry_key: string | null }[];
}

export interface AvailableModel {
  key: string;
  display_name: string;
  available: boolean;
}

export async function assignModelRole(role: string, key: string) {
  const response = await fetch('/api/models/roles', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role, key }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'La sélection du modèle a échoué.');
}

export function useModelSelection(loadModels: boolean, refreshKey?: string | null) {
  const [roles, setRoles] = useState<Record<string, ModelRole>>({});
  const [models, setModels] = useState<AvailableModel[]>([]);
  const [error, setError] = useState('');
  const [pending, setPending] = useState('');
  const [modelsLoading, setModelsLoading] = useState(false);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const response = await fetch('/api/models/roles', { signal });
    if (!response.ok) throw new Error('La configuration des modèles est indisponible.');
    const result = await response.json();
    if (!signal?.aborted) setRoles(result.roles || {});
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal).catch(failure => {
      if (!controller.signal.aborted) setError(String(failure));
    });
    return () => controller.abort();
  }, [refresh, refreshKey, loadModels]);

  useEffect(() => {
    if (!loadModels) return;
    const controller = new AbortController();
    setModelsLoading(true);
    void fetch('/api/models', { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('La liste des modèles est indisponible.');
      const result = await response.json();
      if (!controller.signal.aborted) setModels(result.models || []);
    }).catch(failure => {
      if (!controller.signal.aborted) setError(String(failure));
    }).finally(() => { if (!controller.signal.aborted) setModelsLoading(false); });
    return () => controller.abort();
  }, [loadModels]);

  const assign = async (role: string, key: string) => {
    setPending(role);
    setError('');
    try {
      await assignModelRole(role, key);
      await refresh();
      return true;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
      return false;
    } finally { setPending(''); }
  };

  return { roles, models, error, pending, modelsLoading, assign };
}
