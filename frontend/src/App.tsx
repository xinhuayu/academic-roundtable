import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { api, exportUrl } from "./api";
import type { AppMetadata, ConversationProfile, DocumentDependencies, EvaluationRatings, Job, LearningEvaluationBundle, Message, ProviderHealth, Session, Speaker, StreamEvent } from "./types";

const speakerMeta: Record<Speaker, { monogram: string; subtitle: string }> = {
  Momo: { monogram: "M", subtitle: "tests and challenges" },
  Bobby: { monogram: "B", subtitle: "develops the case" },
  Sam: { monogram: "S", subtitle: "academic host" },
  System: { monogram: "∴", subtitle: "roundtable recap" },
};

const profileMeta: Record<ConversationProfile, { label: string; short: string }> = {
  fast: { label: "Fast discussion", short: "Fast" },
  research: { label: "Research mode", short: "Research" },
  verification: { label: "Verification mode", short: "Verification" },
};

type VoiceState = "idle" | "recording" | "transcribing";

function voiceTime(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function preferredVoiceMimeType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"]
    .find((value) => MediaRecorder.isTypeSupported(value)) ?? "";
}

export function VoiceInputControl({
  state,
  busy,
  seconds,
  draftReady,
  disabled,
  onToggle,
}: {
  state: VoiceState;
  busy: boolean;
  seconds: number;
  draftReady: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="voice-input-row" aria-live="polite">
      <button
        type="button"
        className={`voice-input-button ${state === "recording" ? "is-recording" : ""}`}
        onClick={onToggle}
        disabled={disabled || state === "transcribing"}
      >
        {state === "recording" ? "Stop recording" : busy ? "Interrupt and speak" : "Voice input"}
      </button>
      <span>{state === "recording"
        ? `Recording ${voiceTime(seconds)} · select Stop recording when finished`
        : state === "transcribing"
          ? "AI is transcribing and lightly correcting terminology…"
          : draftReady
            ? "Voice draft ready — review and edit before Answer"
            : "Record until you stop · audio is sent to OpenAI and not saved"}</span>
    </div>
  );
}

function formatDigest(value: unknown): string {
  if (!value) return "Not developed yet.";
  if (typeof value === "string") return value || "Not developed yet.";
  if (Array.isArray(value)) return value.length ? value.join(" · ") : "—";
  return JSON.stringify(value, null, 2);
}

function Badge({ children, tone = "neutral" }: { children: React.ReactNode; tone?: string }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

function ProfileChoice({
  value,
  onChange,
  disabled = false,
  compact = false,
}: {
  value: ConversationProfile;
  onChange: (profile: ConversationProfile) => void;
  disabled?: boolean;
  compact?: boolean;
}) {
  return (
    <div className={`profile-choice ${compact ? "profile-choice-compact" : ""}`} role="group" aria-label="AI LLM mode">
      {(Object.keys(profileMeta) as ConversationProfile[]).map((profile) => (
        <button
          key={profile}
          type="button"
          className={value === profile ? "is-selected" : ""}
          aria-pressed={value === profile}
          disabled={disabled}
          title={profile === "fast"
            ? "Current provider models with the shortest response time"
            : profile === "research"
              ? "Flagship models with medium reasoning, deeper 140–220-word turns, and enlarged budgets"
              : "Flagship models with high reasoning for verification and the hardest claims"}
          onClick={() => onChange(profile)}
        >
          {compact ? profileMeta[profile].short : profileMeta[profile].label}
        </button>
      ))}
    </div>
  );
}

export function buildDigestStatusMessages(jobs: Job[]): Message[] {
  return jobs
    .filter((job) => ["topic_digest", "conversation_digest"].includes(job.kind) && ["queued", "running"].includes(job.status))
    .map((job) => ({
      id: `ephemeral-${job.id}`,
      speaker: "System",
      content: job.kind === "topic_digest" ? "Topic summarizing…" : "Conversation summarizing…",
      status: "working",
      target: "roundtable",
      metadata: { kind: "ephemeral_digest_status", job_id: job.id },
      created_at: job.id,
      temporary: true,
    }));
}

function Participant({ health, route }: { health: ProviderHealth; route?: ActiveModelRoute }) {
  const tone = health.reachable ? "ready" : health.configured ? "warning" : "danger";
  return (
    <div className="participant" title={route ? `${profileMeta[route.profile].label}: ${route.model}, ${route.reasoning_effort} reasoning` : health.detail}>
      <span className={`status-dot status-${tone}`} />
      <span><strong>{health.participant}{route && <em>{profileMeta[route.profile].short}</em>}</strong><small>{route?.model || health.model}</small></span>
    </div>
  );
}

type ActiveModelRoute = {
  profile: ConversationProfile;
  model: string;
  reasoning_effort: string;
};

function MentionText({ text }: { text: string }) {
  return <>{text.split(/(@?(?:Momo|Bobby|Sam))\b/gi).map((part, index) => {
    const name = part.replace(/^@/, "").toLowerCase();
    if (!["momo", "bobby", "sam"].includes(name)) return part;
    return <span className={`mention mention-${name}`} key={`${index}-${part}`}>{part}</span>;
  })}</>;
}

function HighlightMentions({ text, breakSamQuestions = false }: { text: string; breakSamQuestions?: boolean }) {
  if (!breakSamQuestions) return <MentionText text={text} />;
  return <>{text.split(/(\bSam[,:，：]\s*[^\n?？]*[?？])/gi).map((part, index) => {
    if (/^Sam[,:，：]\s*[^\n?？]*[?？]$/i.test(part.trim())) {
      return <span className="sam-question" key={`sam-question-${index}`}><MentionText text={part.trim()} /></span>;
    }
    return part ? <MentionText text={part} key={`question-text-${index}`} /> : null;
  })}</>;
}

export function FormattedMessageContent({ text, breakSamQuestions = false }: { text: string; breakSamQuestions?: boolean }) {
  const provenanceLabels = "Background knowledge|Background information|Inference|Speculation|背景知识|背景知識|背景信息|背景資訊|推论|推論|推断|推斷|推测|推測|Inferencia|Especulación|Connaissances générales|Inférence|Spéculation|Hintergrundwissen|Schlussfolgerung|Spekulation|Conhecimento de fundo|Inferência|Especulação";
  const parts = text.split(new RegExp(`(\\*{0,2}(?:${provenanceLabels})[:：]\\*{0,2})`, "gi"));
  const rendered: React.ReactNode[] = [];
  for (let index = 0; index < parts.length; index += 1) {
    const part = parts[index];
    const marker = part.match(new RegExp(`^\\*{0,2}(${provenanceLabels})[:：]\\*{0,2}$`, "i"));
    if (!marker) {
      if (part) rendered.push(<HighlightMentions text={part} breakSamQuestions={breakSamQuestions} key={`text-${index}`} />);
      continue;
    }
    const label = marker[1];
    const content = parts[index + 1] ?? "";
    index += 1;
    if (/^(?:background|背景|conocimiento de fondo|connaissances générales|hintergrundwissen|conhecimento de fundo)/i.test(label)) {
      const questionIndex = breakSamQuestions ? content.search(/\bSam[,:，：]\s*[^\n?？]*[?？]/i) : -1;
      const backgroundContent = (questionIndex >= 0 ? content.slice(0, questionIndex) : content).trim();
      const questionContent = questionIndex >= 0 ? content.slice(questionIndex).trim() : "";
      rendered.push(
        <span className="background-knowledge" key={`background-${index}`}>
          <strong>{label}:</strong>
          <HighlightMentions text={backgroundContent} />
        </span>,
      );
      if (questionContent) {
        rendered.push(
          <span className="after-background-question" key={`background-question-${index}`}>
            <HighlightMentions text={questionContent} breakSamQuestions />
          </span>,
        );
      }
    } else {
      const isInference = /^(?:inference|inferencia|inférence|schlussfolgerung|inferência|推论|推論|推断|推斷)$/i.test(label);
      rendered.push(
        <span className={isInference ? "provenance-block inference-block" : undefined} key={`provenance-${index}`}>
          <strong className="provenance-label">{label}:</strong>
          <HighlightMentions text={content} breakSamQuestions={breakSamQuestions} />
        </span>,
      );
    }
  }
  return <>{rendered}</>;
}

export function TranscriptMessage({ message }: { message: Message }) {
  const meta = speakerMeta[message.speaker] ?? speakerMeta.System;
  const ephemeralSystem = message.metadata.kind === "ephemeral_digest_status";
  const model = typeof message.metadata.model === "string" ? message.metadata.model : "";
  const profile = typeof message.metadata.profile === "string" ? message.metadata.profile : "";
  const reasoning = typeof message.metadata.reasoning_effort === "string" ? message.metadata.reasoning_effort : "";
  return (
    <article className={`message message-${message.speaker.toLowerCase()} ${message.temporary ? "is-streaming" : ""} ${ephemeralSystem ? "is-ephemeral-system" : ""}`}>
      <div className="avatar" aria-hidden="true">{meta.monogram}</div>
      <div className="message-body">
        <header>
          <div><strong>{message.speaker}</strong><span>{ephemeralSystem ? "background task" : meta.subtitle}</span>{model && <span className="message-model-route">{model} · {profile || "fast"} · {reasoning || "default"} reasoning</span>}</div>
          {message.status !== "complete" && <Badge tone="warning">{message.status}</Badge>}
        </header>
        <div className="message-content">{message.content ? <FormattedMessageContent text={message.content} breakSamQuestions={message.speaker === "Momo" || message.speaker === "Bobby"} /> : <span className="thinking">thinking…</span>}</div>
      </div>
    </article>
  );
}


export function NewSessionForm({
  onCreate,
  busy,
  documentDependencies,
}: {
  onCreate: (topic: string, goal: string, profile: ConversationProfile, sources: File[]) => void;
  busy: boolean;
  documentDependencies: DocumentDependencies | null;
}) {
  const [topic, setTopic] = useState("");
  const [goal, setGoal] = useState("Explore the topic deeply, compare explanations, and identify what remains uncertain.");
  const [profile, setProfile] = useState<ConversationProfile>("fast");
  const [sources, setSources] = useState<File[]>([]);
  const pdfReady = Boolean(documentDependencies?.pymupdf && documentDependencies?.pdfplumber);
  const blockedPdf = sources.some((file) => file.name.toLowerCase().endsWith(".pdf")) && documentDependencies !== null && !pdfReady;
  const canSubmit = topic.trim().length >= 3 && !busy && !blockedPdf;

  const addSources = (files: FileList | null) => {
    if (!files) return;
    setSources((current) => {
      const next = [...current];
      for (const file of Array.from(files)) {
        const duplicate = next.some((item) => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified);
        if (!duplicate) next.push(file);
      }
      return next;
    });
  };

  return (
    <form className="new-session" onSubmit={(event) => {
      event.preventDefault();
      if (!canSubmit) return;
      onCreate(topic.trim(), goal.trim(), profile, sources);
    }}>
      <label>Roundtable topic<textarea value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="e.g., When can an observational estimate support a causal interpretation?" rows={3} /></label>
      <label>Sam’s learning goal<textarea value={goal} onChange={(event) => setGoal(event.target.value)} rows={2} /></label>
      <div className="profile-field"><span>AI LLM mode</span><ProfileChoice value={profile} onChange={setProfile} /><small>Choose Fast for quick exploration, Research for deeper 140–220-word mathematical or methodological turns, or Verification for high-depth checking.</small></div>
      <section className="landing-source-panel" aria-labelledby="landing-source-title">
        <div>
          <span className="eyebrow" id="landing-source-title">Source documents · optional</span>
          <p>Select sources now. After Start, extracted sections are sent to the configured model server for digestion while Momo and Bobby greet Sam; ordinary discussion then uses the processed digest.</p>
        </div>
        <label className="upload-zone landing-upload-zone">
          <input type="file" multiple accept=".pdf,.txt,.md,.markdown" onChange={(event) => { addSources(event.target.files); event.currentTarget.value = ""; }} />
          <span>+ Select sources</span>
          <small>PDF, TXT, or Markdown · 30 MB each</small>
        </label>
        {sources.length > 0 && <div className="landing-source-list">{sources.map((file) => <div key={`${file.name}-${file.size}-${file.lastModified}`}><span><strong>{file.name}</strong><small>{Math.max(1, Math.round(file.size / 1024)).toLocaleString()} KB · queued after Start</small></span><button type="button" onClick={() => setSources((current) => current.filter((item) => item !== file))} aria-label={`Remove ${file.name}`}>Remove</button></div>)}</div>}
        {blockedPdf && <div className="dependency-warning"><strong>PDF selection needs setup:</strong> install PyMuPDF and pdfplumber, then restart the app. TXT and Markdown remain available.</div>}
      </section>
      <p className="form-hint">Research and verification modes allow more model work and may take longer. Raw source excerpts are only reopened when Sam explicitly asks to check the original document.</p>
      <p className="retention-warning">This app keeps one local roundtable at a time.</p>
      <button className="button button-primary" disabled={!canSubmit}>Start roundtable</button>
    </form>
  );
}

function LearningEvaluationPanel({
  bundle,
  busy,
  onSave,
  onClose,
}: {
  bundle: LearningEvaluationBundle;
  busy: boolean;
  onSave: (ratings: EvaluationRatings) => Promise<void>;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<EvaluationRatings>(() => structuredClone(bundle.ratings));
  const scored = Object.values(draft.ratings).filter((item) => item.score !== null).length;
  const dimensions = Object.keys(bundle.rubric).length;
  const updateRating = (name: string, field: "score" | "evidence", value: number | null | string) => {
    setDraft((current) => ({
      ...current,
      ratings: {
        ...current.ratings,
        [name]: { ...current.ratings[name], [field]: value },
      },
    }));
  };
  const updateReflection = (field: keyof EvaluationRatings, value: string) => {
    setDraft((current) => ({ ...current, [field]: value }));
  };
  const displayValue = (value: unknown) => {
    if (value === null || value === undefined) return "—";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  };

  return (
    <section className="learning-evaluation" aria-labelledby="learning-evaluation-title">
      <div className="evaluation-heading">
        <div>
          <div className="eyebrow">Learning-quality evaluation</div>
          <h2 id="learning-evaluation-title">Did this roundtable improve your understanding?</h2>
          <p>Score each dimension from 1 to 5 and record a brief example from the conversation. Automated indicators are review aids, not proof of learning.</p>
        </div>
        <button className="text-button" type="button" onClick={onClose}>Close</button>
      </div>

      {bundle.report.human_review?.weighted_score !== null && bundle.report.human_review?.weighted_score !== undefined && (
        <div className="evaluation-score"><strong>{bundle.report.human_review.weighted_score}</strong><span>weighted score / 5</span></div>
      )}

      <div className="rubric-grid">
        {Object.entries(bundle.rubric).map(([name, definition]) => {
          const rating = draft.ratings[name] ?? { score: null, evidence: "", note: definition.question };
          return (
            <fieldset className="rubric-item" key={name}>
              <legend>{definition.label}<small>weight {definition.weight}</small></legend>
              <p>{definition.question}</p>
              <label>
                Score
                <select value={rating.score ?? ""} onChange={(event) => updateRating(name, "score", event.target.value ? Number(event.target.value) : null)}>
                  <option value="">Not scored</option>
                  <option value="1">1 · Counterproductive</option>
                  <option value="2">2 · Weak</option>
                  <option value="3">3 · Adequate</option>
                  <option value="4">4 · Strong</option>
                  <option value="5">5 · Exceptional</option>
                </select>
              </label>
              <label>
                Conversation evidence
                <textarea rows={2} value={rating.evidence} onChange={(event) => updateRating(name, "evidence", event.target.value)} placeholder="A brief moment or example supporting this score" />
              </label>
            </fieldset>
          );
        })}
      </div>

      <div className="evaluation-reflections">
        <label>Most valuable moment<textarea rows={2} value={draft.most_valuable_moment} onChange={(event) => updateReflection("most_valuable_moment", event.target.value)} /></label>
        <label>Most confusing moment<textarea rows={2} value={draft.most_confusing_moment} onChange={(event) => updateReflection("most_confusing_moment", event.target.value)} /></label>
        <label>One change for the next roundtable<textarea rows={2} value={draft.one_change_for_next_run} onChange={(event) => updateReflection("one_change_for_next_run", event.target.value)} /></label>
        <label>Overall comment<textarea rows={2} value={draft.overall_comment} onChange={(event) => updateReflection("overall_comment", event.target.value)} /></label>
      </div>

      <details className="automated-diagnostics">
        <summary>View automated diagnostics and quality gates</summary>
        <div className="diagnostic-grid">
          {Object.entries(bundle.report.automated_diagnostics).map(([name, value]) => <div key={name}><span>{name.replaceAll("_", " ")}</span><strong>{displayValue(value)}</strong></div>)}
        </div>
        <div className="gate-list">
          {Object.entries(bundle.report.quality_gates).map(([name, gate]) => <div key={name} className={`gate gate-${gate.status}`}><strong>{gate.status}</strong><span>{gate.description}</span></div>)}
        </div>
      </details>

      <div className="evaluation-actions">
        <span>{scored} of {dimensions} dimensions scored{bundle.saved ? " · saved evaluation" : ""}</span>
        <button className="button button-primary" type="button" disabled={busy} onClick={() => onSave(draft)}>{busy ? "Saving…" : "Save evaluation"}</button>
      </div>
    </section>
  );
}

function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [health, setHealth] = useState<ProviderHealth[]>([]);
  const [documentDependencies, setDocumentDependencies] = useState<DocumentDependencies | null>(null);
  const [appMetadata, setAppMetadata] = useState<AppMetadata | null>(null);
  const [activeModelRoutes, setActiveModelRoutes] = useState<Partial<Record<"Momo" | "Bobby", ActiveModelRoute>>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [composer, setComposer] = useState("");
  const [composerInputMethod, setComposerInputMethod] = useState<"text" | "voice">("text");
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [voiceSeconds, setVoiceSeconds] = useState(0);
  const [voiceDraftReady, setVoiceDraftReady] = useState(false);
  const [target, setTarget] = useState("roundtable");
  const [rounds, setRounds] = useState(2);
  const [automaticRoundVariation, setAutomaticRoundVariation] = useState(true);
  const [activeRound, setActiveRound] = useState<number | null>(null);
  const [recordDownloaded, setRecordDownloaded] = useState(false);
  const [evaluation, setEvaluation] = useState<LearningEvaluationBundle | null>(null);
  const [evaluationBusy, setEvaluationBusy] = useState(false);
  const [confirmNewSession, setConfirmNewSession] = useState(false);
  const [pendingLandingSession, setPendingLandingSession] = useState<{ topic: string; goal: string; profile: ConversationProfile; sources: File[] } | null>(null);
  const conversationPanel = useRef<HTMLElement>(null);
  const transcriptViewport = useRef<HTMLDivElement>(null);
  const composerInput = useRef<HTMLTextAreaElement>(null);
  const pendingStart = useRef<{ rounds: number; speaker?: "Momo" | "Bobby" } | null>(null);
  const discardedSessionIds = useRef(new Set<string>());
  const wasBusy = useRef(false);
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const mediaStream = useRef<MediaStream | null>(null);
  const voiceChunks = useRef<Blob[]>([]);
  const voiceBytes = useRef(0);
  const voiceStoppedForSize = useRef(false);
  const voiceTicker = useRef<number | null>(null);
  const discardVoiceCapture = useRef(false);

  const refreshSession = async (id = session?.id) => {
    if (!id) return;
    const current = await api.getSession(id);
    setSession(current);
  };

  useEffect(() => {
    Promise.all([api.listSessions(), api.health(), api.documentDependencies(), api.meta()])
      .then(([available, healthResponse, dependencies, metadata]) => {
        setHealth(healthResponse.providers);
        setDocumentDependencies(dependencies);
        setAppMetadata(metadata);
        return available[0] ? api.getSession(available[0].id) : null;
      })
      .then((current) => current && setSession(current))
      .catch((cause) => setError(cause.message));
  }, []);

  useEffect(() => () => {
    discardVoiceCapture.current = true;
    if (mediaRecorder.current?.state === "recording") mediaRecorder.current.stop();
    mediaStream.current?.getTracks().forEach((track) => track.stop());
    if (voiceTicker.current !== null) window.clearInterval(voiceTicker.current);
  }, []);

  useEffect(() => {
    if (!session) return;
    setActiveModelRoutes({});
    setRecordDownloaded(false);
    setEvaluation(null);
    setConfirmNewSession(false);
    const frame = window.requestAnimationFrame(() => {
      conversationPanel.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      const viewport = transcriptViewport.current;
      if (viewport) viewport.scrollTop = viewport.scrollHeight;
      composerInput.current?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [session?.id]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const viewport = transcriptViewport.current;
      if (!viewport) return;
      viewport.scrollTop = viewport.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [session?.messages, busy, session?.jobs.filter((job) => ["topic_digest", "conversation_digest"].includes(job.kind) && ["queued", "running"].includes(job.status)).length]);

  useEffect(() => {
    if (!busy) return;
    const frame = window.requestAnimationFrame(() => {
      conversationPanel.current?.scrollIntoView({ behavior: "auto", block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [busy]);

  useEffect(() => {
    const AIJustReturnedFloor = wasBusy.current && !busy && session?.state === "HUMAN_FLOOR";
    wasBusy.current = busy;
    if (!AIJustReturnedFloor) return;
    let secondFrame = 0;
    const firstFrame = window.requestAnimationFrame(() => {
      secondFrame = window.requestAnimationFrame(() => {
        const viewport = transcriptViewport.current;
        if (viewport) viewport.scrollTop = viewport.scrollHeight;
        composerInput.current?.focus({ preventScroll: true });
      });
    });
    return () => {
      window.cancelAnimationFrame(firstFrame);
      if (secondFrame) window.cancelAnimationFrame(secondFrame);
    };
  }, [busy, session?.state]);
  useEffect(() => {
    if (!session || !session.jobs.some((job) => ["queued", "running"].includes(job.status))) return;
    const timer = window.setInterval(() => refreshSession(session.id).catch(() => undefined), 2500);
    return () => window.clearInterval(timer);
  }, [session?.id, session?.jobs]);

  const activeJobs = useMemo(() => session?.jobs.filter((job) => ["queued", "running"].includes(job.status)) ?? [], [session?.jobs]);
  const activeFinalSummaryJob = activeJobs.find((job) => job.kind === "final_summary");
  const activeOnePageSummaryJob = activeJobs.find((job) => job.kind === "one_page_summary");
  const recapActive = activeJobs.some((job) => job.kind === "conversation_digest");
  const digestStatusMessages = useMemo(() => buildDigestStatusMessages(activeJobs), [activeJobs]);
  const conversationMessages = useMemo(() => session?.messages.filter((message) => !(message.speaker === "System" && message.metadata.kind === "recap")) ?? [], [session?.messages]);
  const recapMessages = useMemo(() => session?.messages.filter((message) => message.speaker === "System" && ["recap", "final_summary"].includes(String(message.metadata.kind))) ?? [], [session?.messages]);
  const hasSamDirection = useMemo(() => session?.messages.some((message) => message.speaker === "Sam" && message.metadata.kind !== "session_opening") ?? false, [session?.messages]);
  const concluded = session?.state === "CLOSING" || session?.state === "CLOSED";
  const pdfDependenciesReady = Boolean(documentDependencies?.pymupdf && documentDependencies?.pdfplumber);
  const voiceMaxBytes = appMetadata?.voice_input?.max_audio_bytes ?? 25 * 1024 * 1024;
  const chooseRoundCount = () => automaticRoundVariation ? (Math.random() < 0.2 ? 3 : 2) : rounds;

  const enqueueInitialSources = async (sessionId: string, sources: File[]) => {
    for (const file of sources) {
      try {
        await api.upload(sessionId, file);
        const refreshed = await api.getSession(sessionId);
        setSession((current) => current?.id === sessionId ? refreshed : current);
      } catch (cause) {
        setError(`Could not add ${file.name}: ${(cause as Error).message}`);
      }
    }
  };

  const createSession = async (topic: string, learningGoal: string, profile: ConversationProfile = "fast", forceReset = false, initialSources: File[] = []) => {
    setBusy(true); setError("");
    try {
      const created = await api.createSession({
        topic,
        learning_goal: learningGoal,
        rounds_per_segment: automaticRoundVariation ? 2 : rounds,
        sources_only: false,
        periodic_summary: true,
        conversation_profile: profile,
        force_reset: forceReset,
      });
      setSession(created);
      if (initialSources.length > 0) void enqueueInitialSources(created.id, initialSources);
    } catch (cause) { setError((cause as Error).message); } finally { setBusy(false); }
  };

  const requestLandingSession = async (topic: string, learningGoal: string, profile: ConversationProfile, sources: File[]) => {
    if (busy) return;
    setError("");
    try {
      const existing = await api.listSessions();
      if (existing.length > 0) {
        setPendingLandingSession({ topic, goal: learningGoal, profile, sources });
        return;
      }
      await createSession(topic, learningGoal, profile, false, sources);
    } catch (cause) {
      setError((cause as Error).message);
    }
  };

  const confirmLandingReset = async () => {
    if (!pendingLandingSession || busy) return;
    const draft = pendingLandingSession;
    setPendingLandingSession(null);
    await createSession(draft.topic, draft.goal, draft.profile, true, draft.sources);
  };

  const handleStreamEvent = (event: StreamEvent, streamState: { tempId?: string }) => {
    if (event.type === "round_start") setActiveRound(event.round_number ?? null);
    if (event.type === "message_start" && event.speaker) {
      if ((event.speaker === "Momo" || event.speaker === "Bobby") && event.profile && event.model) {
        setActiveModelRoutes((current) => ({
          ...current,
          [event.speaker as "Momo" | "Bobby"]: {
            profile: event.profile as ConversationProfile,
            model: event.model as string,
            reasoning_effort: event.reasoning_effort || "default",
          },
        }));
      }
      streamState.tempId = `stream-${Date.now()}-${event.speaker}`;
      const temporary: Message = { id: streamState.tempId, speaker: event.speaker, content: "", status: "streaming", target: "roundtable", metadata: { profile: event.profile, model: event.model, reasoning_effort: event.reasoning_effort }, created_at: new Date().toISOString(), temporary: true };
      setSession((current) => current && ({ ...current, messages: [...current.messages, temporary] }));
    }
    if (event.type === "delta" && streamState.tempId && event.text) {
      setSession((current) => current && ({ ...current, messages: current.messages.map((message) => message.id === streamState.tempId ? { ...message, content: message.content + event.text } : message) }));
    }
    if (event.type === "message_complete" && streamState.tempId && event.message && typeof event.message !== "string") {
      setSession((current) => current && ({ ...current, messages: current.messages.map((message) => message.id === streamState.tempId ? event.message as Message : message) }));
      streamState.tempId = undefined;
    }
    if (event.type === "provider_error") setError(`${event.speaker}: ${event.message}`);
  };

  const startDiscussion = async (requestedRounds?: number, startingSpeaker?: "Momo" | "Bobby", continueWithoutSam = false) => {
    if (!session || busy) return;
    const segmentRounds = requestedRounds ?? chooseRoundCount();
    setBusy(true); setError("");
    const streamState: { tempId?: string } = {};
    try {
      await api.streamSegment(session.id, segmentRounds, (event) => handleStreamEvent(event, streamState), startingSpeaker, continueWithoutSam);
      await refreshSession(session.id);
    } catch (cause) {
      if (!discardedSessionIds.current.has(session.id)) {
        setError((cause as Error).message);
        await refreshSession(session.id).catch(() => undefined);
      }
    }
    finally {
      setBusy(false); setActiveRound(null);
      const pending = pendingStart.current;
      if (pending) {
        pendingStart.current = null;
        window.setTimeout(() => startDiscussion(pending.rounds, pending.speaker), 0);
      }
    }
  };

  const sendMessage = async (event: FormEvent) => {
    event.preventDefault();
    if (!session || !composer.trim()) return;
    const content = composer.trim(); setComposer(""); setError("");
    try {
      const plannedRounds = chooseRoundCount();
      const action = await api.message(session.id, { content, target, continue_rounds: plannedRounds, input_method: composerInputMethod });
      setComposerInputMethod("text");
      setVoiceDraftReady(false);
      await refreshSession(session.id);
      if (action.suggested_action === "start_segment") {
        const speaker = action.starting_speaker === "Momo" || action.starting_speaker === "Bobby" ? action.starting_speaker : undefined;
        const continueRounds = Number(action.continue_rounds ?? plannedRounds);
        if (busy) pendingStart.current = { rounds: continueRounds, speaker };
        else await startDiscussion(continueRounds, speaker);
      }
    } catch (cause) { setError((cause as Error).message); }
  };

  const interrupt = async () => { if (session) await api.interrupt(session.id); };
  const stopVoiceRecording = (discard = false) => {
    discardVoiceCapture.current = discard;
    if (mediaRecorder.current?.state === "recording") mediaRecorder.current.stop();
  };
  const startVoiceRecording = async () => {
    if (!session || concluded || voiceState !== "idle") return;
    setError("");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("Voice input is not supported by this browser. Use a current browser or type Sam's response.");
      return;
    }
    try {
      if (busy) await api.interrupt(session.id);
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      const mimeType = preferredVoiceMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      mediaRecorder.current = recorder;
      mediaStream.current = stream;
      voiceChunks.current = [];
      voiceBytes.current = 0;
      voiceStoppedForSize.current = false;
      discardVoiceCapture.current = false;
      setVoiceDraftReady(false);
      setVoiceSeconds(0);
      recorder.ondataavailable = (event) => {
        if (event.data.size <= 0) return;
        const nextSize = voiceBytes.current + event.data.size;
        if (nextSize <= voiceMaxBytes) {
          voiceChunks.current.push(event.data);
          voiceBytes.current = nextSize;
        }
        if (nextSize >= Math.floor(voiceMaxBytes * 0.95) && recorder.state === "recording") {
          voiceStoppedForSize.current = true;
          recorder.stop();
        }
      };
      recorder.onstop = async () => {
        if (voiceTicker.current !== null) window.clearInterval(voiceTicker.current);
        voiceTicker.current = null;
        mediaStream.current?.getTracks().forEach((track) => track.stop());
        mediaStream.current = null;
        mediaRecorder.current = null;
        if (discardVoiceCapture.current) {
          voiceChunks.current = [];
          setVoiceState("idle");
          setVoiceSeconds(0);
          return;
        }
        const recordedType = recorder.mimeType || "audio/webm";
        const blob = new Blob(voiceChunks.current, { type: recordedType });
        voiceChunks.current = [];
        voiceBytes.current = 0;
        if (!blob.size) {
          setVoiceState("idle");
          setError("No audio was captured. Check microphone permission and try again.");
          return;
        }
        if (voiceStoppedForSize.current) {
          setError("Recording reached the transcription service's audio-size capacity and stopped automatically. The captured audio is being transcribed.");
        }
        setVoiceState("transcribing");
        try {
          const extension = recordedType.includes("mp4") ? "m4a" : recordedType.includes("ogg") ? "ogg" : "webm";
          const result = await api.transcribeVoice(
            session.id,
            new File([blob], `sam-voice-${Date.now()}.${extension}`, { type: recordedType }),
          );
          setComposer((current) => `${current.trim()}${current.trim() ? "\n\n" : ""}${result.text}`.slice(0, 24000));
          setComposerInputMethod("voice");
          setVoiceDraftReady(true);
          window.requestAnimationFrame(() => composerInput.current?.focus({ preventScroll: true }));
        } catch (cause) {
          setError((cause as Error).message);
        } finally {
          setVoiceState("idle");
        }
      };
      recorder.start(1000);
      setVoiceState("recording");
      const startedAt = Date.now();
      voiceTicker.current = window.setInterval(
        () => setVoiceSeconds(Math.floor((Date.now() - startedAt) / 1000)),
        500,
      );
    } catch (cause) {
      mediaStream.current?.getTracks().forEach((track) => track.stop());
      mediaStream.current = null;
      setVoiceState("idle");
      setError(cause instanceof DOMException && cause.name === "NotAllowedError"
        ? "Microphone permission was not granted. Allow access or type Sam's response."
        : `Could not start voice input: ${(cause as Error).message}`);
    }
  };
  const requestRecap = async () => {
    if (!session || recapActive) return;
    setError("");
    try {
      await api.interrupt(session.id);
      await api.recap(session.id);
      await refreshSession(session.id);
    } catch (cause) {
      setError((cause as Error).message);
    }
  };
  const toggleSetting = async (key: "sources_only" | "periodic_summary", value: boolean) => { if (session) setSession(await api.updateSession(session.id, { [key]: value })); };
  const updateConversationProfile = async (value: ConversationProfile) => {
    if (!session || busy) return;
    setActiveModelRoutes({});
    setSession(await api.updateSession(session.id, { conversation_profile: value }));
  };
  const upload = async (file: File) => {
    if (!session) return;
    const isPdf = file.name.toLowerCase().endsWith(".pdf");
    if (isPdf && documentDependencies && !pdfDependenciesReady) {
      setError(
        "PDF source parsing requires pymupdf + pdfplumber in this runtime. Install them and retry, or upload a TXT/Markdown file.",
      );
      return;
    }
    setError("");
    try {
      await api.upload(session.id, file);
      await refreshSession(session.id);
    } catch (cause) {
      setError((cause as Error).message);
    }
  };
  const endSession = async () => {
    if (!session || concluded) return;
    pendingStart.current = null;
    setError("");
    try {
      setSession(await api.closeSession(session.id));
    } catch (cause) { setError((cause as Error).message); }
  };
  const cancelSummary = async () => {
    if (!session || session.state !== "CLOSING") return;
    setError("");
    try {
      setSession(await api.cancelFinalSummary(session.id));
    } catch (cause) { setError((cause as Error).message); }
  };
  const openEvaluation = async () => {
    if (!session || session.state !== "CLOSED") return;
    setEvaluationBusy(true); setError("");
    try {
      setEvaluation(await api.getLearningEvaluation(session.id));
    } catch (cause) { setError((cause as Error).message); }
    finally { setEvaluationBusy(false); }
  };
  const saveEvaluation = async (ratings: EvaluationRatings) => {
    if (!session || session.state !== "CLOSED") return;
    setEvaluationBusy(true); setError("");
    try {
      const saved = await api.saveLearningEvaluation(session.id, ratings);
      setEvaluation(saved);
      setRecordDownloaded(false);
      await refreshSession(session.id);
    } catch (cause) { setError((cause as Error).message); }
    finally { setEvaluationBusy(false); }
  };
  const clearSessionAndBeginNew = async () => {
    if (!session) { setError(""); return; }
    setError("");
    setConfirmNewSession(false);
    pendingStart.current = null;
    discardedSessionIds.current.add(session.id);
    try {
      await api.purgeSessions();
      setSession(null);
      setComposer("");
      setComposerInputMethod("text");
      setVoiceDraftReady(false);
      setRecordDownloaded(false);
      setEvaluation(null);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      if (session) discardedSessionIds.current.delete(session.id);
    }
  };
  const requestNewRoundtable = () => {
    if (!session) { setError(""); return; }
    const finalJob = session.jobs.find((job) => job.kind === "final_summary");
    const summaryWasSkipped = ["cancelled", "interrupted"].includes(finalJob?.status ?? "");
    const needsConfirmation = session.state === "CLOSING" || summaryWasSkipped || !recordDownloaded;
    if (needsConfirmation) setConfirmNewSession(true);
    else void clearSessionAndBeginNew();
  };

  const finalSummary = [...(session?.messages ?? [])].reverse().find((message) => message.metadata.kind === "final_summary");
  const finalSummaryJob = session?.jobs.find((job) => job.kind === "final_summary");
  const summaryCancelled = finalSummaryJob?.status === "cancelled";
  const summaryInterrupted = finalSummaryJob?.status === "interrupted";
  const onePageSummary = [...(session?.summary_history ?? [])]
    .reverse()
    .find((digest) => digest.kind === "one_page" && typeof digest.digest?.content === "string")?.digest?.content;
  const displayedProfile = activeModelRoutes.Momo?.profile || activeModelRoutes.Bobby?.profile || session?.conversation_profile || "fast";
  const configuredProfile = appMetadata?.conversation_profiles?.find((profile) => profile.id === displayedProfile);
  const displayedRoutes = (["Momo", "Bobby"] as const).reduce((routes, participant) => {
    const live = activeModelRoutes[participant];
    const configured = configuredProfile?.participants[participant];
    const base = health.find((item) => item.participant === participant);
    routes[participant] = live ?? {
      profile: displayedProfile,
      model: configured?.model || base?.model || "not configured",
      reasoning_effort: configured?.reasoning_effort || "default",
    };
    return routes;
  }, {} as Record<"Momo" | "Bobby", ActiveModelRoute>);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <img src="/academic-roundtable-logo.png" alt="Academic Roundtable" />
          <span><strong>Academic Roundtable</strong><small>deep conversations for better learning</small></span>
        </div>
        <div className="top-participants">
          {health.map((item) => <Participant key={item.participant} health={item} route={session && (item.participant === "Momo" || item.participant === "Bobby") ? displayedRoutes[item.participant] : undefined} />)}
          <div className="participant sam-participant"><span className="status-dot status-ready" /><span><strong>Sam</strong><small>academic host</small></span></div>
        </div>
        <div className="session-nav">
          {session && !concluded
            ? <button className="button button-stop" onClick={endSession} disabled={voiceState !== "idle"}>End</button>
            : <span className="session-status">{session ? "Session closeout" : "New roundtable"}</span>}
        </div>
      </header>

      {!session ? (
        <main className="empty-stage">
          <img className="hero-logo" src="/academic-roundtable-logo.png" alt="Momo, Bobby, and Sam in conversation" />
          <div className="empty-copy"><div className="eyebrow">New inquiry</div><h1>Put a difficult idea at the center of the table.</h1><p>Momo and Bobby debate the substance. Sam questions, judges, and guides where the learning goes next.</p><NewSessionForm onCreate={requestLandingSession} busy={busy} documentDependencies={documentDependencies} /></div>
          {pendingLandingSession && (
            <div className="new-session-confirm" role="dialog" aria-labelledby="landing-reset-title" aria-modal="true">
              <div>
                <strong id="landing-reset-title">Start a fresh roundtable?</strong>
                <p>This will purge all previous local sessions, summaries, and source uploads before opening the new session.</p>
              </div>
              <div className="new-session-confirm-actions">
                <button className="button button-ghost" onClick={() => setPendingLandingSession(null)}>Keep planning</button>
                <button className="button button-stop" onClick={confirmLandingReset} disabled={busy}>Purge and start</button>
              </div>
            </div>
          )}
        </main>
      ) : concluded ? (
        <main className="close-session-page">
          <section className="close-session-card">
            <div className="close-icon">✓</div>
            <div className="eyebrow">Session closeout</div>
            <h1>{session.state === "CLOSING" ? "Preparing your final record…" : summaryCancelled ? "Session ended · summary skipped" : summaryInterrupted ? "Session ended · summary interrupted" : "Session concluded"}</h1>
            <p>{session.state === "CLOSING" ? "The final summary is being assembled from the retained digest history. You may cancel it and keep the transcript and existing digests." : summaryCancelled ? "Summary generation was cancelled. Your transcript, existing digests, and sources remain available below until you start another roundtable." : summaryInterrupted ? "The application restarted before summary generation finished. The transcript and all completed digests remain available below." : "Your complete conversation is ready to download. Save anything you want to keep before starting another roundtable."}</p>
            {error && <div className="error-banner"><span>{error}</span><button onClick={() => setError("")}>Dismiss</button></div>}
            {session.state === "CLOSING" && (
              <div className="summary-progress-message" role="status" aria-live="polite">
                <div className="summary-progress-symbol" aria-hidden="true">{activeOnePageSummaryJob ? "1P" : "Σ"}</div>
                <div>
                  <strong>{activeOnePageSummaryJob ? "Generating the one-page summary" : "Summarizing the session materials"}<span className="summary-progress-dots" aria-hidden="true">......</span></strong>
                  <span>{activeOnePageSummaryJob?.detail || activeFinalSummaryJob?.detail || "Reviewing the retained conversation and digest history"}. Please wait; you may cancel summary generation if you do not need it.</span>
                </div>
              </div>
            )}
            <div className="close-stats">
              <div><strong>{session.completed_rounds}</strong><span>rounds</span></div>
              <div><strong>{session.messages.length}</strong><span>messages</span></div>
              <div><strong>{session.summary_history.length}</strong><span>digests</span></div>
              <div><strong>{session.documents.length}</strong><span>sources</span></div>
            </div>
            {finalSummary && <div className="final-summary-preview"><div className="eyebrow">Final summary</div><FormattedMessageContent text={finalSummary.content} /></div>}
            {!finalSummary && <div className="final-summary-preview wrapup-preview"><div className="eyebrow">Current discussion wrap-up</div><h3>{formatDigest(session.conversation_digest.active_question || session.active_question)}</h3><dl className="digest-list"><div><dt>Agreements</dt><dd>{formatDigest(session.conversation_digest.agreements)}</dd></div><div><dt>Disagreements</dt><dd>{formatDigest(session.conversation_digest.disagreements)}</dd></div><div><dt>Open questions</dt><dd>{formatDigest(session.conversation_digest.open_questions)}</dd></div></dl></div>}
            <div className="close-downloads">
              {session.state === "CLOSED" ? <>
                <a className="button button-primary" href={exportUrl(session.id, "archive")} download onClick={() => setRecordDownloaded(true)}>Save complete archive</a>
                <a className="button button-secondary" href={exportUrl(session.id, "markdown")} download onClick={() => setRecordDownloaded(true)}>Download readable transcript</a>
                {onePageSummary ? (
                  <a className="button button-ghost" href={exportUrl(session.id, "one_page_summary")} download onClick={() => setRecordDownloaded(true)}>Download one-page summary</a>
                ) : <button className="button button-ghost" disabled>Preparing one-page summary…</button>}
                <a className="button button-ghost" href={exportUrl(session.id, "summary_digest")} download onClick={() => setRecordDownloaded(true)}>Summary digest</a>
              </> : <><button className="button button-primary" disabled>Preparing downloads…</button><button className="button button-stop" onClick={cancelSummary}>Cancel summary</button></>}
            </div>
            {session.state === "CLOSED" && !evaluation && (
              <div className="evaluation-launch">
                <div><strong>{session.learning_evaluation ? "Learning evaluation saved" : "Reflect on the learning"}</strong><span>{session.learning_evaluation ? `Weighted score: ${session.learning_evaluation.report.human_review?.weighted_score ?? "incomplete"} / 5` : "Evaluate focus, intellectual progress, readability, and what you learned."}</span></div>
                <button className="button button-secondary" disabled={evaluationBusy} onClick={openEvaluation}>{evaluationBusy ? "Opening…" : session.learning_evaluation ? "View or update evaluation" : "Evaluate learning"}</button>
              </div>
            )}
            {session.state === "CLOSED" && evaluation && <LearningEvaluationPanel key={evaluation.updated_at ?? "new-evaluation"} bundle={evaluation} busy={evaluationBusy} onSave={saveEvaluation} onClose={() => setEvaluation(null)} />}
            {confirmNewSession && (
              <div className="new-session-confirm" role="dialog" aria-labelledby="new-session-confirm-title" aria-modal="true">
                <div>
                  <strong id="new-session-confirm-title">Stay to save or evaluate this session?</strong>
                  <p>This will purge this and all previous local sessions, summaries, and source uploads. None of these steps is required.</p>
                </div>
                <div className="new-session-confirm-actions">
                  <button className="button button-ghost" onClick={() => setConfirmNewSession(false)}>Yes, stay here</button>
                  <button className="button button-stop" onClick={clearSessionAndBeginNew}>Start new roundtable and purge old</button>
                </div>
              </div>
            )}
            <div className="new-session-handoff">
              <button className="button button-primary new-roundtable-button" onClick={requestNewRoundtable}>Start a new roundtable</button>
              <small>{recordDownloaded ? "A download was requested. Starting the next table now clears this local session." : "Downloading, reading the summary, and evaluating learning are optional. You may proceed directly to a new table."}</small>
            </div>
          </section>
        </main>
      ) : (
        <main className="workspace">
          <section className="topic-bar">
            <div><div className="eyebrow">Active inquiry</div><h1>{session.topic}</h1><p>{session.learning_goal}</p></div>
            <div className="topic-actions"><div className="topic-mode-control"><span>AI LLM mode · next segment</span><ProfileChoice value={session.conversation_profile} onChange={updateConversationProfile} disabled={busy} compact /></div><span className="language-indicator"><strong>{session.conversation_language || "English"}</strong> conversation</span><span><strong>{session.completed_rounds}</strong> rounds</span></div>
          </section>

          {error && <div className="error-banner"><span>{error}</span><button onClick={() => setError("")}>Dismiss</button></div>}
          {activeJobs.length > 0 && <div className="job-strip">{activeJobs.slice(0, 2).map((job: Job) => <div key={job.id}><span className="spinner" /><strong>{job.kind.replaceAll("_", " ")}</strong><span>{job.detail}</span></div>)}</div>}

          <section className={`conversation-card ${busy ? "is-live" : ""}`} ref={conversationPanel}>
            <div className="conversation-heading"><h2><span className="eyebrow">Conversation</span><span className="conversation-name conversation-name-momo">Momo</span><span className="conversation-separator">·</span><span className="conversation-name conversation-name-bobby">Bobby</span><span className="conversation-separator">·</span><span className="conversation-name conversation-name-sam">Sam</span></h2><div className="conversation-model-route" title="The model route selected or actually reported by the live segment"><strong>{profileMeta[displayedProfile].label}</strong><span>Momo · {displayedRoutes.Momo.model} · {displayedRoutes.Momo.reasoning_effort}</span><span>Bobby · {displayedRoutes.Bobby.model} · {displayedRoutes.Bobby.reasoning_effort}</span></div><div className={busy ? "live-indicator active" : concluded ? "live-indicator" : "live-indicator sam-floor"}>{busy ? `Round ${activeRound ?? "…"} live` : concluded ? "Session concluded" : "Sam has the floor"}</div></div>
            <div className="conversation-layout">
              <div className="transcript" ref={transcriptViewport} aria-live="polite">
                {conversationMessages.map((message) => <TranscriptMessage key={message.id} message={message} />)}
                {digestStatusMessages.map((message) => <TranscriptMessage key={message.id} message={message} />)}
              </div>

              <aside className="host-panel" aria-label="Sam's host controls">
                <div className="host-panel-heading"><div className="avatar">S</div><strong>Sam</strong><span className="host-label-separator" aria-hidden="true">·</span><small>Guide the roundtable</small></div>
                <form onSubmit={sendMessage} className={`composer ${(!busy && !concluded) || voiceState !== "idle" ? "sam-has-floor" : ""} ${voiceState !== "idle" ? `voice-${voiceState}` : ""}`}>
                  <div className="composer-topline"><label>Address <select value={target} onChange={(event) => setTarget(event.target.value)}><option value="roundtable">Automatic</option><option value="Momo">Momo</option><option value="Bobby">Bobby</option><option value="both">Both independently</option></select></label><span>Names and @mentions override</span></div>
                  <VoiceInputControl
                    state={voiceState}
                    busy={busy}
                    seconds={voiceSeconds}
                    draftReady={voiceDraftReady}
                    disabled={concluded || appMetadata?.voice_input?.configured === false}
                    onToggle={() => voiceState === "recording" ? stopVoiceRecording() : startVoiceRecording()}
                  />
                  <div className="composer-actions">
                    {!concluded && <div className="quick-actions"><button type="button" onClick={requestRecap} disabled={recapActive}>Recap</button><button type="button" onClick={() => { setComposerInputMethod("text"); setVoiceDraftReady(false); setComposer("What evidence would distinguish these explanations?"); }}>Evidence</button><button type="button" onClick={() => { setComposerInputMethod("text"); setVoiceDraftReady(false); setComposer(`Return to the active question: ${session.active_question}`); }}>Refocus</button></div>}
                    <button type="submit" className="button button-primary composer-submit" disabled={concluded || voiceState !== "idle" || !composer.trim()}>{concluded ? "Ended" : "Answer"}</button>
                  </div>
                  <textarea ref={composerInput} disabled={concluded || voiceState === "transcribing"} maxLength={24000} value={composer} onChange={(event) => setComposer(event.target.value)} placeholder={concluded ? "This session has concluded. The complete record is ready to export." : hasSamDirection ? "Ask, challenge, judge, or redirect…" : "Greet Momo and Bobby, then set the first scientific direction…"} rows={8} />
                </form>
                <div className="segment-controls">
                  <label>AI rounds <select value={automaticRoundVariation ? "auto" : String(rounds)} onChange={(event) => { const value = event.target.value; setAutomaticRoundVariation(value === "auto"); if (value !== "auto") setRounds(Number(value)); }} disabled={busy}><option value="auto">Auto · usually 2</option>{[2, 3, 4, 5].map((value) => <option key={value} value={value}>{value} fixed</option>)}</select></label>
                  <button className="button button-stop" onClick={interrupt} disabled={!busy}>Interrupt AI</button>
                  <button className="button button-secondary" onClick={() => startDiscussion(undefined, undefined, true)} disabled={busy || concluded || !hasSamDirection} title="Continue without answering the AI's question">Let them continue</button>
                </div>
              </aside>
            </div>
          </section>

          <section className="below-grid">
            <article className="info-card"><div className="section-heading"><span className="eyebrow">Topic digest</span><Badge>{String(session.topic_digest.status ?? "active")}</Badge></div><h3>{String(session.topic_digest.central_question ?? session.topic)}</h3><dl className="digest-list"><div><dt>Key concepts</dt><dd>{formatDigest(session.topic_digest.key_concepts)}</dd></div><div><dt>Scope</dt><dd>{formatDigest(session.topic_digest.scope)}</dd></div><div><dt>Perspectives</dt><dd>{formatDigest(session.topic_digest.theoretical_perspectives)}</dd></div></dl></article>
            <article className="info-card summary-card"><div className="section-heading"><span className="eyebrow">Summary history</span><Badge>{session.summary_history?.length ? `${session.summary_history.length} saved` : "pending"}</Badge></div><dl className="digest-list"><div><dt>Active thread</dt><dd>{formatDigest(session.conversation_digest.active_question || session.active_question)}</dd></div><div><dt>Agreements</dt><dd>{formatDigest(session.conversation_digest.agreements)}</dd></div><div><dt>Disagreements</dt><dd>{formatDigest(session.conversation_digest.disagreements)}</dd></div><div><dt>Open questions</dt><dd>{formatDigest(session.conversation_digest.open_questions)}</dd></div></dl>{recapMessages.map((message) => <div className="visible-recap" key={message.id}><strong>{message.metadata.kind === "final_summary" ? "Final summary" : "Recap"}</strong><p><HighlightMentions text={message.content} /></p></div>)}{!concluded && <button className="text-button" onClick={requestRecap} disabled={recapActive}>Summarize the conversation so far →</button>}</article>
          </section>

          <section className="evidence-card">
            <div>
              <div className="section-heading"><span className="eyebrow">Evidence library</span><Badge>{session.documents.length}</Badge></div>
              <p>Files are stored locally. Extracted sections are sent to the configured model server for digestion; ordinary turns use the processed digest, and raw excerpts return only for Sam's explicit source check.</p>
            </div>
            <label className="upload-zone">
              <input type="file" accept=".pdf,.txt,.md,.markdown" onChange={(event) => event.target.files?.[0] && upload(event.target.files[0])} />
              <span>+ Add a source</span>
              <small>PDF, TXT, or Markdown · 30 MB</small>
            </label>
            {!pdfDependenciesReady && documentDependencies && (
              <div className="dependency-warning">
                <strong>PDF upload blocked:</strong> install PyMuPDF and pdfplumber to enable robust table + figure extraction.
                <div>Detected: PyMuPDF {documentDependencies.pymupdf_version || "not found"}, pdfplumber {documentDependencies.pdfplumber_version || "not found"}.</div>
              </div>
            )}
            <div className="document-list">{session.documents.map((document) => <div key={document.id} className="document-item"><strong>{document.filename}</strong><small>{document.status}{document.error ? ` · ${document.error}` : ""}</small></div>)}</div>
            <div className="settings"><label><input type="checkbox" checked={session.sources_only} onChange={(event) => toggleSetting("sources_only", event.target.checked)} /> Sources only</label><label><input type="checkbox" checked={session.periodic_summary} onChange={(event) => toggleSetting("periodic_summary", event.target.checked)} /> Periodic recap every 5–6 rounds</label></div>
          </section>
        </main>
      )}
    </div>
  );
}

export default App;
