import { requestJson } from "./client.js";

export function analyzeQuestion(question, previousResponseId, context) {
  const safeContext = context || {};
  const options = safeContext.signal ? { signal: safeContext.signal } : undefined;
  return requestJson(
    "/analyze",
    {
      question: question,
      previous_response_id: previousResponseId || null,
      source_tab: safeContext.sourceTab || null,
      subtab: safeContext.subtab || null,
      case_facts: safeContext.caseFacts || null,
    },
    options,
  );
}
