import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { buildDigestStatusMessages, FormattedMessageContent, NewSessionForm } from "./App";


describe("FormattedMessageContent", () => {
  it("starts an inference label in its own block", () => {
    const markup = renderToStaticMarkup(
      <FormattedMessageContent text="The estimate is associated with the outcome. Inference: Causality requires additional assumptions." />,
    );

    expect(markup).toContain('class="provenance-block inference-block"');
    expect(markup).toContain("Inference:");
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
