const API_BASE_URL = "/api";

function buildSessionHeaders(chatSessionId) {
  return {
    "X-Chat-Session-Id": chatSessionId,
  };
}

export async function getChatContextFiles(chatSessionId) {
  const response = await fetch(API_BASE_URL + "/chat/context", {
    method: "GET",
    headers: buildSessionHeaders(chatSessionId),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Kunne ikke hente kontekstfiler");
  }
  return data.files || [];
}

export async function uploadChatContextFile(file, chatSessionId) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(API_BASE_URL + "/chat/context", {
    method: "POST",
    headers: buildSessionHeaders(chatSessionId),
    body: formData,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Kunne ikke uploade kontekstfil");
  }
  return data.files || [];
}

export async function deleteChatContextFile(contextId, chatSessionId) {
  const response = await fetch(API_BASE_URL + "/chat/context/" + encodeURIComponent(contextId), {
    method: "DELETE",
    headers: buildSessionHeaders(chatSessionId),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Kunne ikke fjerne kontekstfil");
  }
  return data.files || [];
}

export async function clearChatContextFiles(chatSessionId) {
  const response = await fetch(API_BASE_URL + "/chat/context", {
    method: "DELETE",
    headers: buildSessionHeaders(chatSessionId),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Kunne ikke rydde kontekstfiler");
  }
  return data.files || [];
}
