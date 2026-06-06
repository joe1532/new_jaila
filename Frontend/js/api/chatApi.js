import { requestJson, requestStream } from "./client.js";

function buildSessionHeaders(chatSessionId) {
  return {
    "X-Chat-Session-Id": chatSessionId,
  };
}

export function sendChat(message, previousResponseId, chatSessionId, options) {
  const safeContext = options && options.context ? options.context : {};
  const opts = {
    headers: buildSessionHeaders(chatSessionId),
  };
  if (options && options.signal) {
    opts.signal = options.signal;
  }
  const payload = {
    message: message,
    previous_response_id: previousResponseId || null,
    use_vector_search: safeContext.useVectorSearch !== false,
    vector_store_ids: Array.isArray(safeContext.vectorStoreIds) ? safeContext.vectorStoreIds : null,
  };
  return requestJson(
    "/chat",
    payload,
    opts,
  );
}

export function sendChatStream(message, previousResponseId, chatSessionId, options, onEvent) {
  const safeContext = options && options.context ? options.context : {};
  const opts = {
    headers: buildSessionHeaders(chatSessionId),
  };
  if (options && options.signal) {
    opts.signal = options.signal;
  }
  const payload = {
    message: message,
    previous_response_id: previousResponseId || null,
    use_vector_search: safeContext.useVectorSearch !== false,
    vector_store_ids: Array.isArray(safeContext.vectorStoreIds) ? safeContext.vectorStoreIds : null,
  };
  return requestStream(
    "/chat",
    payload,
    opts,
    onEvent,
  );
}

export function exportChatPdf(messages, chatSessionId, sources) {
  const safeSources = sources || {};
  return requestJson(
    "/chat/export-pdf",
    {
      messages: messages || [],
      citations: Array.isArray(safeSources.citations) ? safeSources.citations : [],
      retrieval_results: Array.isArray(safeSources.retrievalResults) ? safeSources.retrievalResults : [],
      used_retrieval_results: Array.isArray(safeSources.usedRetrievalResults)
        ? safeSources.usedRetrievalResults
        : [],
      used_vector_store_ids: Array.isArray(safeSources.usedVectorStoreIds) ? safeSources.usedVectorStoreIds : [],
    },
    {
      headers: buildSessionHeaders(chatSessionId),
    },
  );
}
