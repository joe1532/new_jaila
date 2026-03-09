import { requestJson } from "./client.js";

function buildSessionHeaders(chatSessionId) {
  return {
    "X-Chat-Session-Id": chatSessionId,
  };
}

export function sendChat(message, previousResponseId, chatSessionId, options) {
  const opts = {
    headers: buildSessionHeaders(chatSessionId),
  };
  if (options && options.signal) {
    opts.signal = options.signal;
  }
  return requestJson(
    "/chat",
    {
      message: message,
      previous_response_id: previousResponseId || null,
    },
    opts,
  );
}

export function exportChatPdf(messages, chatSessionId) {
  return requestJson(
    "/chat/export-pdf",
    {
      messages: messages || [],
    },
    {
      headers: buildSessionHeaders(chatSessionId),
    },
  );
}
