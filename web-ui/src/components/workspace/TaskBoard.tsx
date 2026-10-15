import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Plus,
  MoreHorizontal,
  Calendar,
  Tag,
  AlertCircle,
  CheckCircle2,
  Circle,
  Clock,
  Trash2,
  GripVertical,
} from 'lucide-react';
import { useAppStore } from '@/store/appStore';
import type { Task, TaskStatus, TaskPriority } from '@/types';

const columns: { id: TaskStatus; label: string; color: string }[] = [
  { id: 'todo', label: 'To Do', color: '#6e6e73' },
  { id: 'in-progress', label: 'In Progress', color: '#0071e3' },
  { id: 'review', label: 'Review', color: '#ff9500' },
  { id: 'done', label: 'Done', color: '#34c759' },
];

const priorityConfig: Record<TaskPriority, { icon: React.ReactNode; color: string; label: string }> = {
  low: {
    icon: <Circle size={12} strokeWidth={2} />,
    color: '#6e6e73',
    label: 'Low',
  },
  medium: {
    icon: <Clock size={12} strokeWidth={2} />,
    color: '#ff9500',
    label: 'Medium',
  },
  high: {
    icon: <AlertCircle size={12} strokeWidth={2} />,
    color: '#ff453a',
    label: 'High',
  },
};

const tagColors: Record<string, string> = {
  design: '#af52de',
  ui: '#0071e3',
  backend: '#5ac8fa',
  dev: '#34c759',
  docs: '#a2845e',
  research: '#5856d6',
  ux: '#ff2d55',
  bug: '#ff453a',
  perf: '#ff9500',
  a11y: '#32ade6',
};

const assigneeColors: Record<string, string> = {
  Alpha: '#0071e3',
  Beta: '#34c759',
  Gamma: '#ff9500',
};

function TaskCard({
  task,
  onDragStart,
  onDragEnd,
  onDelete,
}: {
  task: Task;
  onDragStart: (task: Task) => void;
  onDragEnd: () => void;
  onDelete: (id: string) => void;
}) {
  const [showMenu, setShowMenu] = useState(false);
  const priority = priorityConfig[task.priority];
  const [isDragging, setIsDragging] = useState(false);

  const handleDragStart = (e: React.DragEvent) => {
    setIsDragging(true);
    onDragStart(task);
    e.dataTransfer.effectAllowed = 'move';
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    e.dataTransfer.setData('text/plain', JSON.stringify({ taskId: task.id, offsetX: e.clientX - rect.left, offsetY: e.clientY - rect.top }));
  };

  const handleDragEnd = () => {
    setIsDragging(false);
    onDragEnd();
  };

  return (
    <div
      draggable
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      data-task-id={task.id}
      style={{ opacity: isDragging ? 0.4 : 1 }}
    >
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.95 }}
      transition={{ duration: 0.2 }}
      className="group relative rounded-lg border p-2.5 cursor-grab active:cursor-grabbing transition-shadow duration-150 hover:shadow-md"
      style={{
        backgroundColor: 'var(--bg-surface)',
        borderColor: 'var(--border-subtle)',
      }}
      whileHover={{ y: -1 }}
    >
      {/* Priority indicator - top stripe */}
      <div
        className="absolute top-0 left-0 right-0 h-[2px] rounded-t-lg"
        style={{ backgroundColor: priority.color }}
      />

      {/* Header: priority + menu */}
      <div className="flex items-center justify-between mb-1.5">
        <div
          className="flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider"
          style={{ color: priority.color }}
        >
          {priority.icon}
          {priority.label}
        </div>
        <div className="relative">
          <button
            onClick={() => setShowMenu(!showMenu)}
            className="p-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity duration-150 cursor-pointer"
            style={{ color: 'var(--text-tertiary)' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'var(--bg-icon-hover)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            <MoreHorizontal size={14} />
          </button>

          <AnimatePresence>
            {showMenu && (
              <>
                <div className="fixed inset-0 z-30" onClick={() => setShowMenu(false)} />
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ duration: 0.1 }}
                  className="absolute right-0 top-6 z-40 rounded-lg border py-1 shadow-lg"
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    borderColor: 'var(--border-subtle)',
                    minWidth: '120px',
                  }}
                >
                  <button
                    onClick={() => {
                      onDelete(task.id);
                      setShowMenu(false);
                    }}
                    className="flex items-center gap-2 w-full px-3 py-1.5 text-sm cursor-pointer"
                    style={{ color: '#ff453a' }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.backgroundColor = 'var(--bg-icon-hover)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.backgroundColor = 'transparent';
                    }}
                  >
                    <Trash2 size={12} />
                    Delete
                  </button>
                </motion.div>
              </>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Title */}
      <h4
        className="text-sm font-semibold mb-1 leading-snug"
        style={{ color: 'var(--text-primary)' }}
      >
        {task.title}
      </h4>

      {/* Description */}
      {task.description && (
        <p
          className="text-xs mb-2 line-clamp-2 leading-relaxed"
          style={{ color: 'var(--text-secondary)' }}
        >
          {task.description}
        </p>
      )}

      {/* Tags */}
      {task.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {task.tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium"
              style={{
                backgroundColor: `${tagColors[tag] || '#6e6e73'}18`,
                color: tagColors[tag] || '#6e6e73',
              }}
            >
              <Tag size={8} className="mr-0.5" />
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Footer: assignee + date */}
      <div className="flex items-center justify-between">
        <div
          className="flex items-center gap-1.5 text-[11px] font-medium"
          style={{ color: assigneeColors[task.assignee] || 'var(--text-secondary)' }}
        >
          <span
            className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold"
            style={{
              backgroundColor: `${assigneeColors[task.assignee] || '#6e6e73'}22`,
              color: assigneeColors[task.assignee] || '#6e6e73',
              border: `1.5px solid ${assigneeColors[task.assignee] || '#6e6e73'}44`,
            }}
          >
            {task.assignee.charAt(0)}
          </span>
          {task.assignee}
        </div>
        <div
          className="flex items-center gap-1 text-[10px]"
          style={{ color: 'var(--text-tertiary)' }}
        >
          <Calendar size={10} />
          {new Date(task.createdAt).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
          })}
        </div>
      </div>
    </motion.div>
    </div>
  );
}

function AddTaskForm({
  status,
  onAdd,
  onCancel,
}: {
  status: TaskStatus;
  onAdd: (task: Task) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<TaskPriority>('medium');
  const [tags, setTags] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    const tagList = tags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);

    const assignees = ['Alpha', 'Beta', 'Gamma'];

    onAdd({
      id: `t-${Date.now()}`,
      title: title.trim(),
      description: description.trim(),
      status,
      tags: tagList,
      assignee: assignees[Math.floor(Math.random() * assignees.length)],
      priority,
      createdAt: Date.now(),
    });
  };

  return (
    <motion.form
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2 }}
      onSubmit={handleSubmit}
      className="rounded-lg border p-2.5 space-y-2"
      style={{
        backgroundColor: 'var(--bg-surface)',
        borderColor: 'var(--border-subtle)',
      }}
    >
      <input
        type="text"
        placeholder="Task title..."
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        autoFocus
        className="w-full bg-transparent text-sm font-medium outline-none placeholder:text-[var(--text-tertiary)]"
        style={{ color: 'var(--text-primary)' }}
      />
      <textarea
        placeholder="Description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={2}
        className="w-full bg-transparent text-xs outline-none resize-none placeholder:text-[var(--text-tertiary)]"
        style={{ color: 'var(--text-secondary)' }}
      />
      <input
        type="text"
        placeholder="Tags (comma-separated)"
        value={tags}
        onChange={(e) => setTags(e.target.value)}
        className="w-full bg-transparent text-xs outline-none placeholder:text-[var(--text-tertiary)]"
        style={{ color: 'var(--text-secondary)' }}
      />
      <div className="flex items-center gap-1">
        {(['low', 'medium', 'high'] as TaskPriority[]).map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setPriority(p)}
            className="px-2 py-0.5 rounded-full text-[10px] font-medium transition-all duration-100 cursor-pointer"
            style={{
              backgroundColor: priority === p ? `${priorityConfig[p].color}22` : 'var(--bg-pill)',
              color: priority === p ? priorityConfig[p].color : 'var(--text-tertiary)',
              border: priority === p ? `1px solid ${priorityConfig[p].color}44` : '1px solid transparent',
            }}
          >
            {p}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2 pt-1">
        <button
          type="submit"
          disabled={!title.trim()}
          className="px-3 py-1 rounded-md text-xs font-medium transition-all duration-150 disabled:opacity-40 cursor-pointer"
          style={{
            backgroundColor: 'var(--accent-blue)',
            color: '#fff',
          }}
        >
          Add
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1 rounded-md text-xs font-medium cursor-pointer"
          style={{
            backgroundColor: 'var(--bg-pill)',
            color: 'var(--text-secondary)',
          }}
        >
          Cancel
        </button>
      </div>
    </motion.form>
  );
}

function KanbanColumn({
  column,
  tasks,
  onDrop,
  onAddTask,
  onDeleteTask,
  isDragOver,
  onDragOver,
  onDragLeave,
}: {
  column: (typeof columns)[0];
  tasks: Task[];
  onDrop: (e: React.DragEvent, status: TaskStatus) => void;
  onAddTask: (task: Task) => void;
  onDeleteTask: (id: string) => void;
  isDragOver: boolean;
  onDragOver: () => void;
  onDragLeave: () => void;
}) {
  const [showAddForm, setShowAddForm] = useState(false);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    onDragOver();
  };

  const handleDragLeave = () => {
    onDragLeave();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    onDrop(e, column.id);
  };

  return (
    <div
      className="flex flex-col rounded-lg border transition-colors duration-200 min-w-[160px] sm:min-w-[200px] lg:min-w-[220px] flex-1"
      style={{
        backgroundColor: isDragOver ? `${column.color}08` : 'rgba(255,255,255,0.02)',
        borderColor: isDragOver ? `${column.color}33` : 'var(--border-subtle)',
      }}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Column header */}
      <div
        className="flex items-center justify-between px-2.5 py-2 border-b"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: column.color }}
          />
          <span
            className="text-xs font-semibold uppercase tracking-wider"
            style={{ color: 'var(--text-primary)' }}
          >
            {column.label}
          </span>
          <span
            className="text-[11px] font-medium px-1.5 py-0.5 rounded-full"
            style={{
              backgroundColor: 'var(--bg-pill)',
              color: 'var(--text-tertiary)',
            }}
          >
            {tasks.length}
          </span>
        </div>
        <button
          onClick={() => setShowAddForm(true)}
          className="p-0.5 rounded transition-colors duration-100 opacity-0 group-hover:opacity-100 hover:opacity-100 cursor-pointer"
          style={{ color: 'var(--text-tertiary)' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-icon-hover)';
            e.currentTarget.style.color = 'var(--text-primary)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
            e.currentTarget.style.color = 'var(--text-tertiary)';
          }}
        >
          <Plus size={14} />
        </button>
      </div>

      {/* Tasks */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        <AnimatePresence mode="popLayout">
          {tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              onDragStart={() => {
                // Handled at board level via data attrs
              }}
              onDragEnd={() => {
                // Handled at board level
              }}
              onDelete={onDeleteTask}
            />
          ))}
        </AnimatePresence>

        <AnimatePresence>
          {showAddForm && (
            <AddTaskForm
              status={column.id}
              onAdd={(task) => {
                onAddTask(task);
                setShowAddForm(false);
              }}
              onCancel={() => setShowAddForm(false)}
            />
          )}
        </AnimatePresence>

        <button
          onClick={() => setShowAddForm(true)}
          className="flex items-center gap-1.5 w-full px-3 py-2 rounded-lg text-xs font-medium transition-colors duration-100 cursor-pointer border border-dashed"
          style={{
            color: 'var(--text-tertiary)',
            borderColor: 'var(--border-subtle)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-icon-hover)';
            e.currentTarget.style.color = 'var(--text-secondary)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
            e.currentTarget.style.color = 'var(--text-tertiary)';
          }}
        >
          <Plus size={12} />
          Add task
        </button>
      </div>
    </div>
  );
}

export function TaskBoard() {
  const { tasks, updateTask, addTask, deleteTask } = useAppStore();
  const [dragOverColumn, setDragOverColumn] = useState<TaskStatus | null>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent, status: TaskStatus) => {
      try {
        const data = JSON.parse(e.dataTransfer.getData('text/plain') || '{}');
        if (data.taskId) {
          updateTask(data.taskId, { status });
        }
      } catch {
        const target = e.target as HTMLElement;
        const card = target.closest('[data-task-id]') as HTMLElement | null;
        if (card) {
          updateTask(card.dataset.taskId!, { status });
        }
      }
      setDragOverColumn(null);
    },
    [updateTask]
  );

  const tasksByColumn = React.useMemo(() => {
    const map: Record<TaskStatus, Task[]> = {
      todo: [],
      'in-progress': [],
      review: [],
      done: [],
    };
    tasks.forEach((t) => {
      map[t.status].push(t);
    });
    return map;
  }, [tasks]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Board header */}
      <div
        className="flex items-center justify-between px-3 py-2 border-b flex-shrink-0"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="flex items-center gap-2">
          <CheckCircle2 size={16} strokeWidth={1.5} style={{ color: 'var(--accent-blue)' }} />
          <h3
            className="text-sm font-semibold"
            style={{ color: 'var(--text-primary)' }}
          >
            Task Board
          </h3>
          <span
            className="text-[11px] font-medium px-1.5 py-0.5 rounded-full"
            style={{
              backgroundColor: 'var(--bg-pill)',
              color: 'var(--text-tertiary)',
            }}
          >
            {tasks.length}
          </span>
        </div>
        <div className="flex items-center gap-1 text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
          <GripVertical size={12} />
          <span className="hidden sm:inline">Drag & drop to move</span>
        </div>
      </div>

      {/* Kanban columns */}
      <div className="flex-1 overflow-x-auto overflow-y-hidden p-2">
        <div className="flex gap-2 h-full" style={{ minWidth: `${columns.length * 160}px` }}>
          {columns.map((col) => (
            <KanbanColumn
              key={col.id}
              column={col}
              tasks={tasksByColumn[col.id]}
              onDrop={handleDrop}
              onAddTask={addTask}
              onDeleteTask={deleteTask}
              isDragOver={dragOverColumn === col.id}
              onDragOver={() => setDragOverColumn(col.id)}
              onDragLeave={() => setDragOverColumn(null)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
