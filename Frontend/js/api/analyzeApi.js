import { requestJson } from "./client.js";

export function analyzeQuestion(question, previousResponseId) {
  return requestJson("/analyze", {
    question: question,
    previous_response_id: previousResponseId || null,
  });
}
