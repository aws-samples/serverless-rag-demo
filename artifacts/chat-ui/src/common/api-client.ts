/**
 * Shared client for the authenticated app API.
 *
 * Calls carry the Cognito ID token and nothing else. The API takes the caller's
 * identity from that token, so no request here names the user it is acting for —
 * which is what keeps one user's data out of another user's reach.
 */

import { getRuntimeConfig } from "../runtime-config";

export async function apiRequest<T>(
    path: string,
    idToken: string,
    init: RequestInit = {},
): Promise<T> {
    const base = getRuntimeConfig().apiUrl.replace(/\/+$/, "");
    const response = await fetch(`${base}${path}`, {
        ...init,
        headers: {
            ...(init.body ? { "Content-Type": "application/json" } : {}),
            ...init.headers,
            Authorization: idToken,
        },
    });

    if (!response.ok) {
        // The API returns {"message": "..."} for handled errors.
        let message = response.statusText;
        try {
            const body = await response.json();
            if (body?.message) message = body.message;
        } catch {
            // Non-JSON error body: fall back to the status text.
        }
        throw new Error(message);
    }

    return response.json() as Promise<T>;
}
