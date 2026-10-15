// DiscoverView — the plugin store (step 1 of docs/BRAIN-PLUGINS.md).
// Cards per plugin with live enable/disable; premium plugins and the
// remote registry come later.

import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Puzzle } from 'lucide-react';

const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

interface Plugin {
  id: string;
  name: string;
  version: string;
  description: string;
  category: string;
  capabilities: string[];
  price: string;
  enabled: boolean;
}

export function DiscoverView() {
  const [plugins, setPlugins] = useState<Plugin[]>([]);
  const [notice, setNotice] = useState<string>('');

  const refresh = useCallback(async () => {
    try {
      const data = await fetch('/api/plugins').then((r) => r.json());
      setPlugins(data.plugins || []);
    } catch (e) {
      setPlugins([]);
      setNotice('Catalog unavailable (server offline?)');
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const toggle = async (plugin: Plugin) => {
    setNotice('');
    try {
      const result = await fetch('/api/plugins/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: plugin.id, enabled: !plugin.enabled }),
      }).then((r) => r.json());
      if (result.error) {
        setNotice(result.error);
        return;
      }
      setNotice(
        `${plugin.name} ${result.enabled ? 'enabled' : 'disabled'} ` +
        `(applies: ${result.applies})`
      );
      refresh();
    } catch (e) {
      setNotice('Toggle failed');
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.35, ease: easeOut }}
      className="flex flex-col h-full w-full overflow-y-auto"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <div className="max-w-2xl mx-auto w-full px-4 py-6">
        <div className="flex items-center gap-2 mb-1">
          <Puzzle size={18} style={{ color: 'var(--accent-blue)' }} />
          <h1 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
            Discover
          </h1>
        </div>
        <p className="text-[13px] mb-5" style={{ color: 'var(--text-tertiary)' }}>
          Brain plugins — capabilities you add to your BigBrain.
        </p>

        {notice && (
          <div
            className="px-3 py-2 mb-4 rounded-lg text-[12.5px]"
            style={{
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
            }}
          >
            {notice}
          </div>
        )}

        <div className="flex flex-col gap-3">
          {plugins.length === 0 && (
            <p className="text-[13px]" style={{ color: 'var(--text-tertiary)' }}>
              No plugins in the catalog yet.
            </p>
          )}
          {plugins.map((plugin, index) => (
            <motion.div
              key={plugin.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, delay: index * 0.05, ease: easeOut }}
              className="flex items-center gap-4 px-4 py-3.5 rounded-xl"
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[14px] font-semibold"
                        style={{ color: 'var(--text-primary)' }}>
                    {plugin.name}
                  </span>
                  <span
                    className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded-full"
                    style={{
                      color: 'var(--text-tertiary)',
                      border: '1px solid var(--border-subtle)',
                    }}
                  >
                    {plugin.category}
                  </span>
                  {plugin.price !== 'free' && (
                    <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded-full"
                          style={{
                            color: 'var(--accent-blue)',
                            border: '1px solid var(--accent-blue)',
                          }}>
                      {plugin.price}
                    </span>
                  )}
                </div>
                <p className="text-[12.5px] mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                  {plugin.description}
                </p>
                <p className="text-[11px] mt-1" style={{ color: 'var(--text-tertiary)' }}>
                  {plugin.capabilities.join(' · ')}
                </p>
              </div>
              <button
                onClick={() => toggle(plugin)}
                className="flex-shrink-0 px-4 py-2 rounded-lg text-[13px] font-medium cursor-pointer transition-colors duration-150"
                style={{
                  backgroundColor: plugin.enabled
                    ? 'var(--bg-button)'
                    : 'var(--accent-blue)',
                  color: plugin.enabled ? 'var(--text-primary)' : '#fff',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                {plugin.enabled ? 'Disable' : 'Enable'}
              </button>
            </motion.div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}
