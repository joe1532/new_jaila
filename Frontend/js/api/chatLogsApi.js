import { requestJson } from "./client.js";

// Chat og test-chat har hver sin historik på serveren. Alle kald tager derfor en
// logtype; udelades den, rammer kaldet den almindelige chat-historik som hidtil.
const DEFAULT_KIND = "chat";

export async function saveChatLog(
  user,
  sessionId,
  messages,
  usedModel,
  lastResponseId,
  sources,
  kind = DEFAULT_KIND,
) {
  const safeSources = sources || {};
  return requestJson("/chat-logs", {
    user,
    kind: kind || DEFAULT_KIND,
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

export async function listChatLogs(user, kind = DEFAULT_KIND) {
  return requestJson("/chat-logs", null, {
    method: "GET",
    params: { user, kind: kind || DEFAULT_KIND },
  });
}

export async function getChatLog(user, entryId, kind = DEFAULT_KIND) {
  return requestJson(`/chat-logs/${entryId}`, null, {
    method: "GET",
    params: { user, kind: kind || DEFAULT_KIND },
  });
}

export async function deleteChatLog(user, entryId, kind = DEFAULT_KIND) {
  return requestJson(`/chat-logs/${entryId}`, null, {
    method: "DELETE",
    params: { user, kind: kind || DEFAULT_KIND },
  });
}
