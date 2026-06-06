import { requestJson } from "./client.js";

export async function saveChatLog(
  user,
  sessionId,
  messages,
  usedModel,
  lastResponseId,
  sources,
) {
  const safeSources = sources || {};
  return requestJson("/chat-logs", {
    user,
    session_id: sessionId || "",
    messages: messages || [],
    used_model: usedModel || "",
    last_response_id: lastResponseId || null,
    citations: Array.isArray(safeSources.citations) ? safeSources.citations : [],
    retrieval_results: Array.isArray(safeSources.retrievalResults) ? safeSources.retrievalResults : [],
    used_retrieval_results: Array.isArray(safeSources.usedRetrievalResults)
      ? safeSources.usedRetrievalResults
      : [],
    used_vector_store_ids: Array.isArray(safeSources.usedVectorStoreIds) ? safeSources.usedVectorStoreIds : [],
  });
}

export async function listChatLogs(user) {
  return requestJson("/chat-logs", null, {
    method: "GET",
    params: { user },
  });
}

export async function getChatLog(user, entryId) {
  return requestJson(`/chat-logs/${entryId}`, null, {
    method: "GET",
    params: { user },
  });
}

export async function deleteChatLog(user, entryId) {
  return requestJson(`/chat-logs/${entryId}`, null, {
    method: "DELETE",
    params: { user },
  });
}
