const API_BASE_URL = "/api";

export async function requestJson(path, payload, options) {
  const method = (options && options.method) || "POST";
  const extraHeaders = (options && options.headers) || {};
  const signal = options && options.signal;
  const isGetLike = method.toUpperCase() === "GET" || method.toUpperCase() === "HEAD";
  const fetchOptions = {
    method: method,
    headers: {
      "Content-Type": "application/json",
      ...extraHeaders,
    },
    body: isGetLike ? undefined : JSON.stringify(payload),
  };
  if (signal) {
    fetchOptions.signal = signal;
  }
  const response = await fetch(API_BASE_URL + path, fetchOptions);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || "Ukendt API-fejl");
  }
  return data;
}
