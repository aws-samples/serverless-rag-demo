/**
 * Cognito group membership, read from the ID token in the browser.
 *
 * This is for deciding what to show, not for deciding what is allowed. The API
 * and both AgentCore runtimes re-check the same claim against a signature they
 * verify themselves, so hiding a control here is a courtesy rather than a
 * control: a caller who sends the request anyway gets a 403.
 */

/** Membership of this group grants the shared-corpus view. */
export const SHARED_CORPUS_GROUP = "corpus-readers";

export function callerGroups(userinfo: any): string[] {
    const claim = userinfo?.tokens?.idToken?.payload?.["cognito:groups"];
    if (Array.isArray(claim)) {
        return claim.filter((g): g is string => typeof g === "string");
    }
    if (typeof claim === "string") {
        return claim.split(",").map((g) => g.trim()).filter(Boolean);
    }
    return [];
}

export function mayReadSharedCorpus(userinfo: any): boolean {
    return callerGroups(userinfo).includes(SHARED_CORPUS_GROUP);
}
