/**
 * Answer feedback client.
 *
 * This used to read the day's shared JSONL file from S3 in the browser, append a
 * line and put it back. Every signed-in user could therefore read everyone
 * else's feedback, replace the whole day's file, and lose entries whenever two
 * people voted at once. The API now writes one object per submission and stamps
 * the email from the caller's token, so nothing is shared and nothing is
 * self-reported.
 */

import { apiRequest } from "./api-client";

export interface FeedbackEntry {
    question: string;
    answer: string;
    sources: string[];
    rating: "up" | "down";
}

export async function submitFeedback(
    entry: FeedbackEntry,
    idToken: string,
): Promise<void> {
    await apiRequest<{ recorded: boolean }>("/feedback", idToken, {
        method: "POST",
        body: JSON.stringify(entry),
    });
}
