import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { buildCloseoutProgress, buildDigestStatusMessages, FormattedMessageContent, NewSessionForm, selectTurnReminderVoice, TranscriptMessage, turnReminderText, VoiceInputControl, VoiceReminderControl } from "./App";


describe("FormattedMessageContent", () => {
  it("renders a plain Background label with the italic background style", () => {
    const markup = renderToStaticMarkup(
      <FormattedMessageContent text="Background: A confidence interval describes sampling uncertainty.\n\nInference: The estimate should be interpreted cautiously." />,
    );

    expect(markup).toContain('class="background-knowledge"');
    expect(markup).toContain("confidence interval");
    expect(markup).toContain('class="provenance-block inference-block"');
  });

  it("starts an inference label in its own block", () => {
    const markup = renderToStaticMarkup(
      <FormattedMessageContent text="The estimate is associated with the outcome. Inference: Causality requires additional assumptions." />,
    );

    expect(markup).toContain('class="provenance-block inference-block"');
    expect(markup).toContain("Inference:");
  });

  it("formats translated Chinese provenance labels", () => {
    const markup = renderToStaticMarkup(
      <FormattedMessageContent text="背景知识：轨迹类别是统计模型的产物。\n\n推论：因果解释需要额外假设。" />,
    );

    expect(markup).toContain('class="background-knowledge"');
    expect(markup).toContain('class="provenance-block inference-block"');
    expect(markup).toContain("背景知识");
    expect(markup).toContain("推论");
  });
});

describe("buildDigestStatusMessages", () => {
  it("creates local System messages only while digest jobs are active", () => {
    const messages = buildDigestStatusMessages([
      { id: "topic-1", kind: "topic_digest", status: "running", progress: 0.4, detail: "Working" },
      { id: "conversation-1", kind: "conversation_digest", status: "complete", progress: 1, detail: "Done" },
      { id: "document-1", kind: "document_digest", status: "running", progress: 0.5, detail: "Working" },
    ]);

    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({
      id: "ephemeral-topic-1",
      speaker: "System",
      content: "Topic summarizing…",
      temporary: true,
      metadata: { kind: "ephemeral_digest_status", job_id: "topic-1" },
    });
  });
});

describe("buildCloseoutProgress", () => {
  it("identifies Momo and Bobby as simultaneous closeout authors", () => {
    const progress = buildCloseoutProgress(
      { id: "final", kind: "final_summary", status: "running", progress: 0.4, detail: "Writing Summary Digest" },
      { id: "one", kind: "one_page_summary", status: "running", progress: 0.4, detail: "Writing one-page summary" },
    );

    expect(progress.symbol).toBe("Σ+1P");
    expect(progress.title).toContain("Momo and Bobby");
    expect(progress.title).toContain("Research mode");
    expect(progress.detail).toContain("Momo: Writing Summary Digest");
    expect(progress.detail).toContain("Bobby: Writing one-page summary");
  });

  it("reports Verification only when Sam selected it", () => {
    const progress = buildCloseoutProgress(
      { id: "final", kind: "final_summary", status: "running", progress: 0.4, detail: "Checking claims", payload: { profile: "verification" } },
      undefined,
      "verification",
    );

    expect(progress.title).toContain("Momo is generating");
    expect(progress.title).toContain("Verification mode");
    expect(progress.detail).toContain("Checking claims");
  });
});

describe("NewSessionForm", () => {
  it("places Start roundtable after the learning goal and before mode selection", () => {
    const markup = renderToStaticMarkup(
      <NewSessionForm onCreate={() => undefined} busy={false} documentDependencies={null} />,
    );

    const goalIndex = markup.indexOf("Sam’s learning goal");
    const startIndex = markup.indexOf("Start roundtable");
    const modeIndex = markup.indexOf("AI LLM mode");

    expect(goalIndex).toBeGreaterThanOrEqual(0);
    expect(startIndex).toBeGreaterThan(goalIndex);
    expect(modeIndex).toBeGreaterThan(startIndex);
    expect(markup).toContain('class="button button-secondary landing-start-button"');
  });
});

describe("TranscriptMessage", () => {
  it("shows the actual routed model, mode, and reasoning for an AI turn", () => {
    const markup = renderToStaticMarkup(
      <TranscriptMessage message={{
        id: "m1",
        speaker: "Momo",
        content: "A research-mode contribution.",
        status: "complete",
        target: "roundtable",
        metadata: { model: "gpt-5.6-sol", profile: "research", reasoning_effort: "medium" },
        created_at: "2026-07-22T00:00:00Z",
      }} />,
    );

    expect(markup).toContain("gpt-5.6-sol");
    expect(markup).toContain("research");
    expect(markup).toContain("medium reasoning");
  });

  it("renders an automatic timeout retry as an ephemeral System notice", () => {
    const markup = renderToStaticMarkup(
      <TranscriptMessage message={{
        id: "retry-1",
        speaker: "System",
        content: "Bobby took too long to respond. Retrying once with a longer timeout…",
        status: "retrying",
        target: "roundtable",
        metadata: { kind: "ephemeral_retry_status", participant: "Bobby" },
        created_at: "2026-07-22T00:00:00Z",
        temporary: true,
      }} />,
    );

    expect(markup).toContain("automatic retry");
    expect(markup).toContain("Retrying once");
    expect(markup).toContain("is-ephemeral-system");
  });
});

describe("NewSessionForm", () => {
  it("offers optional multi-file source staging before session creation", () => {
    const markup = renderToStaticMarkup(
      <NewSessionForm
        onCreate={() => undefined}
        busy={false}
        documentDependencies={{ pymupdf: true, pdfplumber: true, pypdf: true }}
      />,
    );

    expect(markup).toContain("Source documents · optional");
    expect(markup).toContain('type="file"');
    expect(markup).toContain("multiple");
    expect(markup).toContain("extracted sections are sent to the configured model server for digestion");
  });
});

describe("VoiceInputControl", () => {
  it("explains the private review-first voice workflow", () => {
    const idle = renderToStaticMarkup(
      <VoiceInputControl state="idle" busy={false} seconds={0} draftReady={false} disabled={false} onToggle={() => undefined} />,
    );
    const recording = renderToStaticMarkup(
      <VoiceInputControl state="recording" busy={false} seconds={305} draftReady={false} disabled={false} onToggle={() => undefined} />,
    );
    const ready = renderToStaticMarkup(
      <VoiceInputControl state="idle" busy={false} seconds={0} draftReady disabled={false} onToggle={() => undefined} />,
    );

    expect(idle).toContain("Record until you stop");
    expect(idle).toContain("audio is sent to OpenAI and not saved");
    expect(recording).toContain("Recording 5:05");
    expect(recording).toContain("select Stop recording when finished");
    expect(recording).toContain("Stop recording");
    expect(ready).toContain("review and edit before Answer");
  });
});

describe("Sam turn reminder", () => {
  const voices = [
    { name: "Microsoft Zira Desktop", lang: "en-US", default: false, localService: true, voiceURI: "zira" },
    { name: "Microsoft David Desktop", lang: "en-US", default: false, localService: true, voiceURI: "david" },
  ] as SpeechSynthesisVoice[];

  it("selects different available system voices after Momo and Bobby", () => {
    expect(selectTurnReminderVoice(voices, "Momo", "English")?.name).toContain("Zira");
    expect(selectTurnReminderVoice(voices, "Bobby", "English")?.name).toContain("David");
    expect(turnReminderText("Chinese")).toContain("Sam");
  });

  it("offers an accessible on/off control in Sam's panel", () => {
    const markup = renderToStaticMarkup(
      <VoiceReminderControl enabled supported onChange={() => undefined} />,
    );
    expect(markup).toContain("Turn reminder");
    expect(markup).toContain('type="checkbox"');
    expect(markup).toContain("checked");
  });
});
