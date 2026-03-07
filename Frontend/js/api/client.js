const API_BASE_URL = "/api";

export async function requestJson(path, payload, options) {
  const method = (options && options.method) || "POST";
  const extraHeaders = (options && options.headers) || {};
  const response = await fetch(API_BASE_URL + path, {
    method: method,
    headers: {
      "Content-Type": "application/json",
      ...extraHeaders,
    },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Ukendt API-fejl");
  }
  return data;
}
