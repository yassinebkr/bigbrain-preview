import { useState, useEffect, useMemo } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useAppStore } from '@/store/appStore';
import type { CanvasOp } from '@/types';
import Card from './genui/Card';
import Stats from './genui/Stats';
import ChartBar from './genui/ChartBar';
import ChartLine from './genui/ChartLine';
import Table from './genui/Table';
import Code from './genui/Code';
import Buttons from './genui/Buttons';
import Form from './genui/Form';
import Hero from './genui/Hero';
import Alert from './genui/Alert';

const COMPONENT_MAP: Record<string, React.ComponentType<any>> = {
  card: Card,
  stats: Stats,
  'chart-bar': ChartBar,
  'chart-line': ChartLine,
  table: Table,
  code: Code,
  buttons: Buttons,
  form: Form,
  hero: Hero,
  alert: Alert,
};

const SIZE_MAP: Record<string, string> = {
  sparkline: 'col-span-6 sm:col-span-3',
  gauge: 'col-span-6 sm:col-span-3',
  progress: 'col-span-6 sm:col-span-3',
  status: 'col-span-6 sm:col-span-3',
  tags: 'col-span-6 sm:col-span-3',
  card: 'col-span-12 sm:col-span-4',
  stats: 'col-span-12 sm:col-span-4',
  alert: 'col-span-12 sm:col-span-4',
  checklist: 'col-span-12 sm:col-span-4',
  kv: 'col-span-12 sm:col-span-4',
  buttons: 'col-span-12 sm:col-span-4',
  'chart-bar': 'col-span-12 sm:col-span-6',
  'chart-line': 'col-span-12 sm:col-span-6',
  table: 'col-span-12 sm:col-span-6',
  code: 'col-span-12 sm:col-span-6',
  hero: 'col-span-12',
  timeline: 'col-span-12',
  accordion: 'col-span-12',
  form: 'col-span-12',
};

export function GenUICanvas() {
  const { canvasOps } = useAppStore();
  const [components, setComponents] = useState<
    Map<string, { type: string; data: Record<string, unknown> }>
  >(new Map());

  useEffect(() => {
    setComponents((prevComponents) => {
      const newMap = new Map(prevComponents);
      canvasOps.forEach((op: CanvasOp) => {
        if (op.op === 'upsert' && op.id)
          newMap.set(op.id, {
            type: op.type || 'card',
            data: op.data || {},
          });
        else if (op.op === 'patch' && op.id) {
          const existing = newMap.get(op.id);
          if (existing)
            newMap.set(op.id, {
              ...existing,
              data: { ...existing.data, ...op.data },
            });
        } else if (op.op === 'remove' && op.id) newMap.delete(op.id);
        else if (op.op === 'clear') newMap.clear();
      });
      return newMap;
    });
  }, [canvasOps]);

  const items = useMemo(
    () => Array.from(components.entries()),
    [components]
  );

  return (
    <div className="grid grid-cols-12 gap-3 w-full my-3">
      <AnimatePresence>
        {items.map(([id, comp]) => {
          const Renderer = COMPONENT_MAP[comp.type] || Card;
          const sizeClass = SIZE_MAP[comp.type] || 'col-span-4';
          return (
            <motion.div
              key={id}
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.3 }}
              className={`${sizeClass} rounded-[10px] overflow-hidden`}
              style={{
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
              }}
            >
              <Renderer data={comp.data} />
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
