import { describe, expect, it, vi } from "vitest";

import { SsePayloadError, createSseParser } from "../src/lib/sse";

describe("line-buffered SSE parser", () => {
  it("reconstructs fragmented frames before JSON parsing", () => {
    const onEvent = vi.fn();
    const parser = createSseParser(onEvent);

    parser.feed('event: token\ndata: {"event":"tok');
    expect(onEvent).not.toHaveBeenCalled();
    expect(parser.getBufferedText()).toContain("data:");

    parser.feed('en","token":"Sovereign"}\n\n');
    expect(onEvent).toHaveBeenCalledWith({
      event: "token",
      data: { event: "token", token: "Sovereign" },
      rawData: '{"event":"token","token":"Sovereign"}',
    });
  });

  it("parses multiple complete events from one chunk", () => {
    const events = [];
    const parser = createSseParser((event) => events.push(event));

    parser.feed(
      'event: step_started\ndata: {"event":"step_started","step_name":"A"}\n\n' +
        'event: token\ndata: {"event":"token","token":"B"}\n\n',
    );

    expect(events).toHaveLength(2);
    expect(events[0].data.step_name).toBe("A");
    expect(events[1].data.token).toBe("B");
  });

  it("retains a trailing partial frame until finish", () => {
    const events = [];
    const parser = createSseParser((event) => events.push(event));

    parser.feed('data: {"event":"run_completed","run_id":7}');
    expect(events).toEqual([]);
    expect(parser.getBufferedText()).not.toBe("");

    parser.finish();
    expect(events[0].data).toEqual({ event: "run_completed", run_id: 7 });
  });

  it("raises a controlled error for malformed complete frames", () => {
    const parser = createSseParser(() => {});

    expect(() => parser.feed("data: {broken}\n\n")).toThrow(SsePayloadError);
  });

  it("joins multi-line data fields and ignores comments", () => {
    const events = [];
    const parser = createSseParser((event) => events.push(event));

    parser.feed(': keepalive\r\ndata: {"event":"token",\r\ndata: "token":"ok"}\r\n\r\n');
    expect(events[0].data.token).toBe("ok");
  });
});
