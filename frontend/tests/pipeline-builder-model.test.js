import { describe, expect, it } from "vitest";

import {
  addStage,
  duplicateStage,
  hydratePipelineVersion,
  moveStage,
  removeStage,
  renameStageIdentifier,
  serializeStages,
  setTerminalStage,
} from "../src/lib/pipeline-builder-model";

const providers = [
  {
    identifier: "openrouter",
    adapter_available: true,
    health_status: "available",
    models: [
      {
        identifier: "openrouter/free",
        availability_status: "available",
        output_limit: 4096,
        temperature: { minimum: 0, maximum: 2, default: 0.7 },
        thinking_budget_minimum: null,
        supported_parameters: ["temperature", "max_output_tokens"],
      },
    ],
  },
];

function version() {
  return hydratePipelineVersion({
    id: 1,
    version_number: 1,
    state: "draft",
    stages: [
      {
        stable_identifier: "reader",
        name: "Reader",
        position: 1,
        enabled: true,
        provider_type: "openrouter",
        model_string: "openrouter/free",
        prerequisite_dependencies: [],
        required_capabilities: ["text_generation"],
        input_policy: {},
        output_policy: {},
        is_terminal: false,
      },
      {
        stable_identifier: "final",
        name: "Final",
        position: 2,
        enabled: true,
        provider_type: "openrouter",
        model_string: "openrouter/free",
        prerequisite_dependencies: ["reader"],
        required_capabilities: ["text_generation"],
        input_policy: {},
        output_policy: {},
        is_terminal: true,
      },
    ],
  });
}

describe("pipeline builder graph model", () => {
  it("renames identifiers and rewrites every dependency reference", () => {
    const pipeline = version();
    const result = renameStageIdentifier(pipeline.stages, "reader", "request-reader");

    expect(result.error).toBe("");
    expect(result.identifier).toBe("request-reader");
    expect(result.stages[1].prerequisite_dependencies).toEqual(["request-reader"]);
  });

  it("prevents duplicate stable identifiers", () => {
    const pipeline = version();
    const result = renameStageIdentifier(pipeline.stages, "reader", "final");

    expect(result.error).toMatch(/unique/i);
    expect(result.stages).toBe(pipeline.stages);
  });

  it("removes dangling dependencies and preserves one terminal stage", () => {
    const pipeline = version();
    const withoutFinal = removeStage(pipeline.stages, "final");

    expect(withoutFinal).toHaveLength(1);
    expect(withoutFinal[0].is_terminal).toBe(true);
    expect(withoutFinal[0].position).toBe(1);
  });

  it("duplicates and reorders stages without duplicate positions or terminal stages", () => {
    const pipeline = version();
    const duplicated = duplicateStage(pipeline.stages, "reader");
    const duplicate = duplicated[1];

    expect(duplicate.stable_identifier).toBe("reader-copy");
    expect(duplicate.is_terminal).toBe(false);
    expect(duplicated.map((stage) => stage.position)).toEqual([1, 2, 3]);

    const moved = moveStage(duplicated, duplicate.stable_identifier, 1);
    expect(moved.map((stage) => stage.stable_identifier)).toEqual(["reader", "final", "reader-copy"]);
    expect(moved.map((stage) => stage.position)).toEqual([1, 2, 3]);
  });

  it("adds catalogue-backed stages and makes the chosen terminal exclusive", () => {
    const added = addStage([], providers);
    expect(added[0].provider_type).toBe("openrouter");
    expect(added[0].model_string).toBe("openrouter/free");
    expect(added[0].is_terminal).toBe(true);

    const pipeline = version();
    const switched = setTerminalStage(pipeline.stages, "reader", true);
    expect(switched.find((stage) => stage.stable_identifier === "reader").is_terminal).toBe(true);
    expect(switched.find((stage) => stage.stable_identifier === "final").is_terminal).toBe(false);
  });

  it("serializes policy JSON and rejects non-object policy values", () => {
    const pipeline = version();
    pipeline.stages[0].input_policy_text = '{"mode":"summary"}';
    const serialized = serializeStages(pipeline.stages);
    expect(serialized[0].input_policy).toEqual({ mode: "summary" });
    expect(serialized[0]).not.toHaveProperty("input_policy_text");

    pipeline.stages[0].output_policy_text = "[]";
    expect(() => serializeStages(pipeline.stages)).toThrow(/Output policy.*JSON object/i);
  });
});
