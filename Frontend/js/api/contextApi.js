const API_BASE_URL = "/api";

function buildSessionHeaders(chatSessionId) {
  return {
    "X-Chat-Session-Id": chatSessionId,
  };
}

async function parseApiError(response, fallbackMessage) {
  const rawText = response && typeof response === "object" && "rawText" in response
    ? String(response.rawText || "")
    : "";
  const status = response && typeof response === "object" && "status" in response
    ? response.status
    : 0;
  if (!rawText) return fallbackMessage + (status ? ` (HTTP ${status})` : "");
  try {
    const data = JSON.parse(rawText);
    if (Array.isArray(data.detail)) {
      return data.detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
    }
    return data.detail || fallbackMessage;
  } catch (_err) {
    return fallbackMessage + (status ? ` (HTTP ${status})` : "");
  }
}

async function parseApiJson(response) {
  const rawText = await response.text();
  if (!rawText) return { data: {}, rawText: "" };
  try {
    return { data: JSON.parse(rawText), rawText };
  } catch (_err) {
    return { data: null, rawText };
  }
}

export async function getChatContextFiles(chatSessionId) {
  const response = await fetch(API_BASE_URL + "/chat/context", {
    method: "GET",
    headers: buildSessionHeaders(chatSessionId),
  });
  const parsed = await parseApiJson(response);
  if (!response.ok) {
    throw new Error(
      await parseApiError(
        { rawText: parsed.rawText, status: response.status },
        "Kunne ikke hente kontekstfiler",
      ),
    );
  }
  if (!parsed.data || typeof parsed.data !== "object") {
    throw new Error("Serveren returnerede ugyldig JSON");
  }
  return parsed.data.files || [];
}

export async function uploadChatContextFile(file, chatSessionId) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(API_BASE_URL + "/chat/context", {
    method: "POST",
    headers: buildSessionHeaders(chatSessionId),
    body: formData,
  });
  const parsed = await parseApiJson(response);
  if (!response.ok) {
    throw new Error(
      await parseApiError(
        { rawText: parsed.rawText, status: response.status },
        "Kunne ikke uploade kontekstfil",
      ),
    );
  }
  if (!parsed.data || typeof parsed.data !== "object") {
    throw new Error("Serveren returnerede ugyldig JSON");
  }
  return parsed.data.files || [];
}

export async function deleteChatContextFile(contextId, chatSessionId) {
  const response = await fetch(API_BASE_URL + "/chat/context/" + encodeURIComponent(contextId), {
    method: "DELETE",
    headers: buildSessionHeaders(chatSessionId),
  });
  const parsed = await parseApiJson(response);
  if (!response.ok) {
    throw new Error(
      await parseApiError(
        { rawText: parsed.rawText, status: response.status },
        "Kunne ikke fjerne kontekstfil",
      ),
    );
  }
  if (!parsed.data || typeof parsed.data !== "object") {
    throw new Error("Serveren returnerede ugyldig JSON");
  }
  return parsed.data.files || [];
}

export async function clearChatContextFiles(chatSessionId) {
  const response = await fetch(API_BASE_URL + "/chat/context", {
    method: "DELETE",
    headers: buildSessionHeaders(chatSessionId),
  });
  const parsed = await parseApiJson(response);
  if (!response.ok) {
    throw new Error(
      await parseApiError(
        { rawText: parsed.rawText, status: response.status },
        "Kunne ikke rydde kontekstfiler",
      ),
    );
  }
  if (!parsed.data || typeof parsed.data !== "object") {
    throw new Error("Serveren returnerede ugyldig JSON");
  }
  return parsed.data.files || [];
}
