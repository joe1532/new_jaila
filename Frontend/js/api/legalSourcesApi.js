import { requestJson } from "./client.js";

export function getLegalSourcesCatalog() {
  return requestJson("/legal-sources/catalog", null, {
    method: "GET",
  });
}

export function getLegalSourceSection(sourceId, page = 1) {
  const safeSourceId = encodeURIComponent(String(sourceId || "").trim());
  return requestJson(`/legal-sources/section/${safeSourceId}`, null, {
    method: "GET",
    params: {
      page: String(Math.max(1, Number(page) || 1)),
      chunk_size: "12",
    },
  });
}
