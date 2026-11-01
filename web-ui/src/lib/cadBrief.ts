import type { Attachment } from '@/types';

export interface CadBrief {
  revision: number;
  run_id?: string;
  status: 'clarifying' | 'proposed';
  sources: Attachment[];
  question?: string | null;
  drawing?: { title: string; dimensions: { id: string; label: string; value: number | null; unit: string; origin: string }[]; issues: { id: string; question: string; blocking: boolean }[] } | null;
  exchanges: { message_id?: string; user: string; assistant: string }[];
}
