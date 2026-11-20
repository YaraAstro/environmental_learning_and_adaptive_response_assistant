const launchToken = new URLSearchParams(location.hash.slice(1)).get("token");
if (launchToken) {
  sessionStorage.setItem("elaraToken", launchToken);
  history.replaceState(null, "", location.pathname);
}
const token = sessionStorage.getItem("elaraToken") || "";

export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api/${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    let message = text;
    try {
      const parsed = JSON.parse(text);
      message =
        typeof parsed.detail === "string"
          ? parsed.detail
          : "Check your input and try again.";
    } catch {
      /* Plain-text server error. */
    }
    throw new Error(message || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}
