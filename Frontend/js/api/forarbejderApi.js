import { requestJson, requestStream } from "./client.js";

export function getForarbejderLaws() {
  return requestJson("/forarbejder/laws", null, { method: "GET" });
}

export function getForarbejderVersions(eli) {
  return requestJson("/forarbejder/versions", null, {
    method: "GET",
    params: { eli: String(eli || "").trim() },
  });
}

export function getForarbejderParagraphs(eli) {
  return requestJson("/forarbejder/paragraphs", null, {
    method: "GET",
    params: { eli: String(eli || "").trim() },
  });
}

/**
 * Kør et forarbejdsopslag. Svaret streames, fordi et koldt opslag tager op mod to
 * minutter, og onEvent kaldes med { type: "progress" | "done" | "error", ... }.
 */
export function runForarbejderHistory(eli, paragraph, steps, options, onEvent) {
  const opts = {};
  if (options && options.signal) {
    opts.signal = options.signal;
  }
  return requestStream(
    "/forarbejder/history",
    {
      eli: String(eli || "").trim(),
      paragraph: String(paragraph || "").trim(),
      steps: Math.max(1, Number(steps) || 1),
    },
    opts,
    onEvent,
  );
}
