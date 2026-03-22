import { requestJson, requestStream } from "./client.js";

function buildContextPayload(safeContext) {
  const contextLogIds = Array.isArray(safeContext.contextLogIds)
    ? safeContext.contextLogIds.filter((id) => String(id || "").trim())
    : [];
  const payload = {
    question: safeContext.question,
    previous_response_id: safeContext.previousResponseId || null,
    source_tab: safeContext.sourceTab || null,
    subtab: safeContext.subtab || null,
    case_id: safeContext.caseId || null,
    case_user: safeContext.caseUser || null,
    case_facts: safeContext.caseFacts || null,
    sags_decision_package: safeContext.sagsDecisionPackage || null,
    context_user: safeContext.contextUser || null,
    context_approved: Boolean(safeContext.contextApproved),
    legal_context_blocks: Array.isArray(safeContext.legalContextBlocks)
      ? safeContext.legalContextBlocks
      : null,
    use_semantic_search_with_legal_context: Boolean(safeContext.useSemanticSearchWithLegalContext),
  };
  if (contextLogIds.length > 0) {
    payload.context_log_ids = contextLogIds;
  } else if (safeContext.contextLogId) {
    payload.context_log_id = safeContext.contextLogId;
  }
  return payload;
}

export function analyzeQuestion(question, previousResponseId, context) {
  const safeContext = { ...(context || {}), question, previousResponseId };
  const options = safeContext.signal ? { signal: safeContext.signal } : undefined;
  return requestJson("/analyze", buildContextPayload(safeContext), options);
}

export function analyzeQuestionStream(question, previousResponseId, context, onEvent) {
  const safeContext = { ...(context || {}), question, previousResponseId };
  const options = safeContext.signal ? { signal: safeContext.signal } : {};
  return requestStream("/analyze", buildContextPayload(safeContext), options, onEvent);
}
