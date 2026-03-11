import { requestJson } from "./client.js";

export async function saveChatLog(user, sessionId, messages, usedModel, lastResponseId) {
  return requestJson("/chat-logs", {
    user,
    session_id: sessionId || "",
    messages: messages || [],
    used_model: usedModel || "",
    last_response_id: lastResponseId || null,
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
