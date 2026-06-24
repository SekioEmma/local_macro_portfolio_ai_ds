import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { LocalResearchPreviewPage } from "./LocalResearchPreviewPage";
import type { AIContextManifestResponse } from "../types";

// Mock the api/client module so the research / prompt tabs cannot trigger
// real fetches even if the default tab changes. Catalogue is the default tab
// and short-circuits the effect, but the mock keeps us safe.
vi.mock("../api/client", () => ({
  fetchAIResearchPreview: vi.fn().mockResolvedValue({ data: null, error: null }),
  fetchAIPromptPreview: vi.fn().mockResolvedValue({ data: null, error: null })
}));

const baseManifest: AIContextManifestResponse = {
  generated_at: "2026-06-24T00:00:00Z",
  included_facts: [],
  excluded_facts: [],
  included_model_outputs: [],
  excluded_model_outputs: [],
  portfolio_context_policy: {},
  privacy_policy: {},
  search_policy: {},
  model_destination: { destination: "local_only" },
  persistence_policy: {},
  risk_boundaries: [],
  source_summary: {},
  mode: "local_preview",
  search_enabled: false,
  external_model_called: false,
  search_called: false,
  saved_by_default: false,
  included_fact_count: 0,
  excluded_fact_count: 0,
  included_model_output_count: 0,
  excluded_model_output_count: 0,
  context_stats: {},
  last_generated_at: "2026-06-24T00:00:00Z",
  full_context_catalogue: {
    evidence_cards: [],
    model_output_cards: [],
    excluded_constraint_cards: [],
    total_card_count: 0,
    priority_counts: {},
    source_badge_distribution: {},
    excluded_reason_distribution: {}
  },
  priority_counts: {},
  excluded_reason_distribution: {}
};

describe("LocalResearchPreviewPage smoke", () => {
  it("renders the header in the happy path with a manifest payload", () => {
    render(
      <LocalResearchPreviewPage
        manifest={{ data: baseManifest, error: null }}
        isLoading={false}
      />
    );

    expect(screen.getByText("本地受控投研预览")).toBeInTheDocument();
  });

  it("renders the loading panel when isLoading is true", () => {
    render(
      <LocalResearchPreviewPage
        manifest={{ data: null, error: null }}
        isLoading={true}
      />
    );

    expect(
      screen.getByText("正在读取本地受控投研上下文")
    ).toBeInTheDocument();
  });

  it("renders the error panel when the manifest failed to load", () => {
    render(
      <LocalResearchPreviewPage
        manifest={{ data: null, error: "manifest unavailable" }}
        isLoading={false}
      />
    );

    expect(screen.getByText("本地受控投研预览暂不可用")).toBeInTheDocument();
    expect(screen.getByText(/manifest unavailable/)).toBeInTheDocument();
  });
});
