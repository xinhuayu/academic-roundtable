import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { buildDigestStatusMessages, FormattedMessageContent, NewSessionForm, TranscriptMessage, VoiceInputControl } from "./App";


describe("FormattedMessageContent", () => {
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
