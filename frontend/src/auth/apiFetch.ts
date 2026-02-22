/**
 * Wrapper de fetch() que inyecta el header X-API-Key automáticamente.
 * Usar en lugar de fetch() en toda la app.
 */
import { API_KEY } from "./useAuth";

export function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    if (API_KEY) {
        headers.set("X-API-Key", API_KEY);
    }
    return fetch(input, { ...init, headers });
}
