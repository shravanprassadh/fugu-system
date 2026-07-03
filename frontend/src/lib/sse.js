export class SsePayloadError extends Error {
  constructor(message, rawData) {
    super(message);
    this.name = "SsePayloadError";
    this.rawData = rawData;
  }
}

export function createSseParser(onEvent) {
  let buffer = "";
  let eventName = "message";
  let dataLines = [];

  function dispatch() {
    if (dataLines.length === 0) {
      eventName = "message";
      return;
    }

    const rawData = dataLines.join("\n");
    const resolvedEvent = eventName;
    eventName = "message";
    dataLines = [];

    if (rawData.trim() === "[DONE]") {
      onEvent({ event: "done", data: null, rawData });
      return;
    }

    let data;
    try {
      data = JSON.parse(rawData);
    } catch (error) {
      throw new SsePayloadError("A complete SSE frame contained invalid JSON.", rawData, {
        cause: error,
      });
    }
    onEvent({ event: resolvedEvent, data, rawData });
  }

  function consumeLine(rawLine) {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (line === "") {
      dispatch();
      return;
    }
    if (line.startsWith(":")) {
      return;
    }

    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) {
      value = value.slice(1);
    }

    if (field === "event") {
      eventName = value || "message";
    } else if (field === "data") {
      dataLines.push(value);
    }
  }

  return {
    feed(chunk) {
      buffer += chunk;
      let newlineIndex = buffer.indexOf("\n");
      while (newlineIndex !== -1) {
        consumeLine(buffer.slice(0, newlineIndex));
        buffer = buffer.slice(newlineIndex + 1);
        newlineIndex = buffer.indexOf("\n");
      }
    },
    finish() {
      if (buffer.length > 0) {
        consumeLine(buffer);
        buffer = "";
      }
      dispatch();
    },
    getBufferedText() {
      return buffer;
    },
  };
}
