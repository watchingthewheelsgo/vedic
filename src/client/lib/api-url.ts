/** Keep local Vite proxy paths, map production requests to the configured API origin. */
export function resolveApiUrl(
  path: string,
  base = import.meta.env?.VITE_API_BASE_URL ?? ""
): string {
  if (!base) return path;
  if (!path.startsWith("/api/")) throw new Error("Expected an application API path");
  return `${base.replace(/\/+$/, "")}/${path.slice(5)}`;
}
