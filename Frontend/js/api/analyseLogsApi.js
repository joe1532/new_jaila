import { requestJson } from "./client.js";

export async function saveAnalyseLog(user, data) {
  return requestJson("/analyse-logs", {
    user,
    question: data.question || "",
    answer: data.answer || "",
    citations: data.citations || [],
    retrieval_results: data.retrieval_results || [],
    used_model: data.used_model || "",
    log_question: data.log_question || data.question,
    used_vector_store_ids: data.used_vector_store_ids || null,
    log_pdf_filename: data.log_pdf_filename || null,
    log_pdf_url: data.log_pdf_url || null,
  });
}

export async function listAnalyseLogs(user) {
  return requestJson("/analyse-logs", null, {
    method: "GET",
    params: { user },
  });
}

export async function getAnalyseLog(user, entryId) {
  return requestJson(`/analyse-logs/${entryId}`, null, {
    method: "GET",
    params: { user },
  });
}
