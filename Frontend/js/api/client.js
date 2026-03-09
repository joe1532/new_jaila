const API_BASE_URL = "/api";

/**
 * Kald API med stream=true. Parser SSE og kalder onEvent for hver event.
 * @param {string} path - fx "/analyze"
 * @param {object} payload - request body
 * @param {object} options - { signal, headers }
 * @param {function} onEvent - (event: { type, text?, ... }) => void
 */
export async function requestStream(path, payload, options, onEvent) {
  const url = new URL(API_BASE_URL + path, window.location.origin);
  url.searchParams.set("stream", "true");
  const extraHeaders = (options && options.headers) || {};
  const signal = options && options.signal;
  const res = await fetch(url.toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...extraHeaders },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "API-fejl");
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() || "";
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const raw = line.slice(6);
        if (raw === "[DONE]" || raw === "") continue;
        try {
          const evt = JSON.parse(raw);
          onEvent(evt);
        } catch (_) {
          /* ignorer ugyldig JSON */
        }
      }
    }
  }
  if (buf.trim()) {
    if (buf.startsWith("data: ")) {
      try {
        const evt = JSON.parse(buf.slice(6));
        onEvent(evt);
      } catch (_) {}
    }
  }
}

export async function requestJson(path, payload, options) {
  const method = (options && options.method) || "POST";
  const extraHeaders = (options && options.headers) || {};
  const signal = options && options.signal;
  const params = options && options.params;
  const isGetLike = method.toUpperCase() === "GET" || method.toUpperCase() === "HEAD";
  let url = API_BASE_URL + path;
  if (params && Object.keys(params).length) {
    const q = new URLSearchParams(params);
    url += (path.includes("?") ? "&" : "?") + q.toString();
  }
  const fetchOptions = {
    method: method,
    headers: {
      "Content-Type": "application/json",
      ...extraHeaders,
    },
    body: isGetLike ? undefined : JSON.stringify(payload),
  };
  if (signal) {
    fetchOptions.signal = signal;
  }
  const response = await fetch(url, fetchOptions);
  let data;
  try {
    const text = await response.text();
    data = text ? JSON.parse(text) : {};
  } catch (_) {
    if (!response.ok) {
      throw new Error(`API-fejl ${response.status}: ${response.statusText || "Serveren returnerede ikke JSON"}`);
    }
    throw new Error("Serveren returnerede ugyldig JSON");
  }
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((e) => e.msg || JSON.stringify(e)).join("; ")
      : (data.detail || "Ukendt API-fejl");
    throw new Error(detail);
  }
  return data;
}
