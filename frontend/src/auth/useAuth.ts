/**
 * Simple password-based auth for the frontend.
 * The password is validated against VITE_APP_PASSWORD env var.
 * The API key (VITE_API_KEY) is stored in sessionStorage after a successful login
 * so all fetch() and WebSocket calls can use it without re-prompting.
 *
 * sessionStorage is cleared automatically when the browser tab is closed.
 */

const SESSION_KEY = "pm_auth";
const APP_PASSWORD = import.meta.env.VITE_APP_PASSWORD as string | undefined;
export const API_KEY = import.meta.env.VITE_API_KEY as string | undefined;

export function isAuthenticated(): boolean {
    // If no password is configured, always allow (dev mode)
    if (!APP_PASSWORD) return true;
    return sessionStorage.getItem(SESSION_KEY) === "1";
}

export function login(password: string): boolean {
    if (!APP_PASSWORD || password === APP_PASSWORD) {
        sessionStorage.setItem(SESSION_KEY, "1");
        return true;
    }
    return false;
}

export function logout(): void {
    sessionStorage.removeItem(SESSION_KEY);
}
