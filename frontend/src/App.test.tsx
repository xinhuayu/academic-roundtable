import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { FormattedMessageContent } from "./App";


describe("FormattedMessageContent", () => {
  it("starts an inference label in its own block", () => {
    const markup = renderToStaticMarkup(
      <FormattedMessageContent text="The estimate is associated with the outcome. Inference: Causality requires additional assumptions." />,
    );

    expect(markup).toContain('class="provenance-block inference-block"');
    expect(markup).toContain("Inference:");
  });
});
