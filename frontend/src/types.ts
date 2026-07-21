export type Speaker = "Sam" | "Momo" | "Bobby" | "System";

export interface Message {
  id: string;
  speaker: Speaker;
  content: string;
  status: string;
  target: string;
  metadata: Record<string, unknown>;
  created_at: string;
  temporary?: boolean;
}

export interface DocumentRecord {
  id: string;
  filename: string;
  status: string;
  digest: string;
  error?: string;
}

export interface Job {
  id: string;
  kind: string;
  status: string;
  progress: number;
  detail: string;
  error?: string;
}

export interface Session {
  id: string;
  topic: string;
  learning_goal: string;
  rounds_per_segment: number;
  sources_only: boolean;
  periodic_summary: boolean;
  state: string;
  active_question: string;
  topic_digest: Record<string, unknown>;
  conversation_digest: Record<string, unknown>;
  completed_rounds: number;
  digested_through_round: number;
  messages: Message[];
  documents: DocumentRecord[];
  jobs: Job[];
  summary_history: Array<{
    id: string;
    kind: string;
    through_round: number;
    digest: Record<string, unknown>;
    created_at: string;
  }>;
  learning_evaluation?: {
    report: EvaluationReport;
    ratings: EvaluationRatings;
    updated_at: string;
  } | null;
  updated_at: string;
}

export interface EvaluationRating {
  score: number | null;
  evidence: string;
  note: string;
}

export interface EvaluationRatings {
  schema_version?: number;
  session_id?: string;
  reviewer: string;
  ratings: Record<string, EvaluationRating>;
  most_valuable_moment: string;
  most_confusing_moment: string;
  one_change_for_next_run: string;
  overall_comment: string;
}

export interface EvaluationReport {
  automated_diagnostics: Record<string, unknown>;
  quality_gates: Record<string, { status: string; value: number | null; threshold: number; description: string }>;
  warnings: string[];
  human_review?: {
    weighted_score: number | null;
    completion_rate: number;
  };
}

export interface LearningEvaluationBundle {
  report: EvaluationReport;
  ratings: EvaluationRatings;
  rubric: Record<string, { label: string; weight: number; question: string }>;
  saved: boolean;
  updated_at: string | null;
}

export interface ProviderHealth {
  participant: string;
  configured: boolean;
  reachable: boolean;
  model: string;
  api_style: string;
  detail: string;
}

export interface StreamEvent {
  type: string;
  speaker?: Speaker;
  text?: string;
  message?: Message | string;
  round_number?: number;
  completed_rounds?: number;
  interrupted?: boolean;
  reason?: string;
}
