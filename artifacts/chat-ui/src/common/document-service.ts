/**
 * Document management client.
 *
 * Every S3 and Knowledge Base operation runs server-side behind the app API, so
 * the browser holds no S3 permissions of its own and the owning user's email is
 * not a parameter to any call here.
 */

import { apiRequest } from "./api-client";

export interface DocumentInfo {
    key: string;
    fileName: string;
    userEmail: string;
    size: number;
    lastModified: Date;
    isOwner: boolean;
}

export interface IngestionStatus {
    status: string; // STARTING | IN_PROGRESS | COMPLETE | FAILED | STOPPING | STOPPED
    startedAt?: Date;
    updatedAt?: Date;
    documentsScanned?: number;
    documentsIndexed?: number;
    documentsFailed?: number;
}

function request<T>(path: string, idToken: string, init: RequestInit = {}): Promise<T> {
    return apiRequest<T>(`/documents${path}`, idToken, init);
}

/**
 * List documents.
 * @param idToken - Cognito ID token
 * @param globalView - if true, list every owner's documents; if false, only the caller's.
 *                     Either way only names and owners are returned, never content.
 */
export async function listDocuments(
    idToken: string,
    globalView: boolean = false,
): Promise<DocumentInfo[]> {
    const scope = globalView ? "all" : "mine";
    const { documents } = await request<{ documents: (Omit<DocumentInfo, "lastModified"> & { lastModified: string })[] }>(
        `?scope=${scope}`,
        idToken,
    );

    return documents.map((doc) => ({
        ...doc,
        lastModified: new Date(doc.lastModified),
    }));
}

/**
 * Get a presigned URL for uploading a document.
 *
 * The API decides the key from the verified token, and writes the Knowledge Base
 * metadata sidecar itself, so there is no separate metadata upload step.
 */
export async function getUploadPresignedUrl(
    fileName: string,
    contentType: string,
    idToken: string,
): Promise<string> {
    const { url } = await request<{ url: string; key: string }>("/upload-url", idToken, {
        method: "POST",
        body: JSON.stringify({ fileName, contentType }),
    });
    return url;
}

/**
 * Delete a document and its metadata sidecar. Rejected unless the caller owns it.
 */
export async function deleteDocument(key: string, idToken: string): Promise<void> {
    await request<{ deleted: string }>("", idToken, {
        method: "DELETE",
        body: JSON.stringify({ key }),
    });
}

/**
 * Get a presigned URL for downloading/viewing a document.
 * Rejected unless the caller owns it.
 */
export async function getDownloadPresignedUrl(
    key: string,
    idToken: string,
): Promise<string> {
    const { url } = await request<{ url: string }>("/download-url", idToken, {
        method: "POST",
        body: JSON.stringify({ key }),
    });
    return url;
}

/**
 * Get the latest ingestion job status for the KB.
 */
export async function getIngestionStatus(idToken: string): Promise<IngestionStatus | null> {
    const body = await request<{
        status: string | null;
        startedAt?: string;
        updatedAt?: string;
        documentsScanned?: number;
        documentsIndexed?: number;
        documentsFailed?: number;
    }>("/ingestion-status", idToken);

    if (!body.status) return null;

    return {
        status: body.status,
        startedAt: body.startedAt ? new Date(body.startedAt) : undefined,
        updatedAt: body.updatedAt ? new Date(body.updatedAt) : undefined,
        documentsScanned: body.documentsScanned,
        documentsIndexed: body.documentsIndexed,
        documentsFailed: body.documentsFailed,
    };
}

/**
 * Trigger KB ingestion job after upload/delete to sync the index.
 */
export async function syncKnowledgeBase(idToken: string): Promise<void> {
    await request<{ ingestionJobId: string }>("/sync", idToken, { method: "POST" });
}
