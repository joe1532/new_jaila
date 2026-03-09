import { requestJson } from "./client.js";

export function getSagsLegalBasis(subtab) {
  const safeSubtab = encodeURIComponent(String(subtab || "").trim());
  return requestJson(`/sagsbehandling/legal-basis?subtab=${safeSubtab}`, null, {
    method: "GET",
  });
}
