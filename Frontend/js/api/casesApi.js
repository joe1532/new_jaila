import { requestJson } from "./client.js";

export function createCase(user, title) {
  return requestJson("/cases", {
    user,
    title: title || null,
  });
}

export function listCases(user) {
  return requestJson("/cases", null, {
    method: "GET",
    params: { user },
  });
}

export function getCase(user, caseId) {
  return requestJson(`/cases/${caseId}`, null, {
    method: "GET",
    params: { user },
  });
}

export function updateCase(caseId, payload) {
  return requestJson(`/cases/${caseId}`, payload, {
    method: "PATCH",
  });
}

export function deleteCase(user, caseId) {
  return requestJson(`/cases/${caseId}`, null, {
    method: "DELETE",
    params: { user },
  });
}
