import type { DocumentDependencies, EvaluationRatings, LearningEvaluationBundle, ProviderHealth, Session, StreamEvent } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export const exportUrl = (sessionId: string, format: "markdown" | "json" | "archive" | "one_page_summary" = "markdown") =>
  `${API_BASE}/api/sessions/${sessionId}/export?format=${format}`;

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...options?.headers,
    },
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // Preserve the HTTP status when the response is not JSON.
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  listSessions: () => request<Session[]>("/api/sessions"),
  getSession: (id: string) => request<Session>(`/api/sessions/${id}`),
  createSession: (payload: {
    topic: string;
    learning_goal: string;
    rounds_per_segment: number;
    sources_only: boolean;
    periodic_summary: boolean;
  }) => request<Session>("/api/sessions", { method: "POST", body: JSON.stringify(payload) }),
  updateSession: (id: string, payload: Record<string, unknown>) =>
    request<Session>(`/api/sessions/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  health: () => request<{ status: string; providers: ProviderHealth[] }>("/api/health"),
  documentDependencies: () => request<DocumentDependencies>("/api/documents/dependencies"),
  interrupt: (id: string) =>
    request<{ interrupted: boolean }>(`/api/sessions/${id}/interrupt`, { method: "POST" }),
  closeSession: (id: string) =>
    request<Session>(`/api/sessions/${id}/close`, { method: "POST" }),
  cancelFinalSummary: (id: string) =>
    request<Session>(`/api/sessions/${id}/final-summary/cancel`, { method: "POST" }),
  getLearningEvaluation: (id: string) =>
    request<LearningEvaluationBundle>(`/api/sessions/${id}/learning-evaluation`),
  saveLearningEvaluation: (id: string, ratings: EvaluationRatings) =>
    request<LearningEvaluationBundle>(`/api/sessions/${id}/learning-evaluation`, {
      method: "PUT",
      body: JSON.stringify(ratings),
    }),
  discardSession: (id: string) =>
    request<void>(`/api/sessions/${id}`, { method: "DELETE" }),
  message: (id: string, payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/sessions/${id}/messages`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  recap: (id: string, periodic?: boolean) =>
    request<Record<string, unknown>>(`/api/sessions/${id}/recap`, {
      method: "POST",
      body: JSON.stringify({ periodic }),
    }),
  upload: async (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Record<string, unknown>>(`/api/sessions/${id}/documents`, {
      method: "POST",
      body: form,
    });
  },
  streamSegment: async (
    id: string,
    rounds: number,
    onEvent: (event: StreamEvent) => void,
    startingSpeaker?: "Momo" | "Bobby",
    continueWithoutSam = false,
  ) => {
    const response = await fetch(`${API_BASE}/api/sessions/${id}/segments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rounds, starting_speaker: startingSpeaker, continue_without_sam: continueWithoutSam }),
    });
    if (!response.ok || !response.body) {
      throw new Error(`Unable to start discussion: ${response.status}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        const data = block
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trim())
          .join("");
        if (data) onEvent(JSON.parse(data) as StreamEvent);
      }
      if (done) break;
    }
  },
};
