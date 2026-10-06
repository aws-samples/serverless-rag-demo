/**
 * RAG evaluation client.
 *
 * The dataset upload, job creation and result read all run server-side now. The
 * browser used to call Bedrock and S3 directly, which meant its Cognito role
 * carried bedrock:CreateEvaluationJob and ListEvaluationJobs — actions IAM
 * cannot scope to a resource, so every signed-in user could list every
 * evaluation job in the account and start paid jobs of their own. The API keys
 * jobs and output to the caller's verified token instead, so none of these
 * calls names a user or a bucket.
 */

import { apiRequest } from "./api-client";

export interface EvalQuestion {
    question: string;
    expected_answer?: string;
    context?: string;
}

export interface EvalJobSummary {
    jobId: string;
    jobName: string;
    status: string;
    createdAt: Date;
}

export interface EvalMetricResult {
    metricName: string;
    score: number;
}

export interface EvalQuestionResult {
    question: string;
    generatedAnswer: string;
    metrics: EvalMetricResult[];
}

export interface EvalResults {
    aggregateScores: EvalMetricResult[];
    perQuestion: EvalQuestionResult[];
}

export interface EvalJob extends EvalJobSummary {
    jobArn: string;
}

// Kept in step with ALLOWED_METRICS in the API, which rejects anything else.
export const ALL_METRICS = [
    "Builtin.Correctness",
    "Builtin.Completeness",
    "Builtin.Helpfulness",
    "Builtin.LogicalCoherence",
    "Builtin.Faithfulness",
    "Builtin.ContextRelevance",
    "Builtin.ContextCoverage",
];

export const DEFAULT_METRICS = ["Builtin.Faithfulness", "Builtin.Correctness", "Builtin.Completeness"];

interface JobResponse {
    jobId: string;
    jobArn: string;
    jobName: string;
    status?: string;
    createdAt?: string;
}

function toJob(body: JobResponse): EvalJob {
    return {
        jobId: body.jobId,
        jobArn: body.jobArn,
        jobName: body.jobName,
        status: body.status || "InProgress",
        createdAt: body.createdAt ? new Date(body.createdAt) : new Date(),
    };
}

/**
 * Start an evaluation of the Knowledge Base over the given questions.
 *
 * The API writes the dataset, names the job and picks its output location, all
 * derived from the caller's token.
 */
export async function createEvalJob(
    questions: EvalQuestion[],
    metrics: string[],
    idToken: string,
): Promise<EvalJob> {
    const body = await apiRequest<JobResponse>("/evaluations", idToken, {
        method: "POST",
        body: JSON.stringify({ questions, metrics }),
    });
    return toJob(body);
}

/**
 * Get the status of one of the caller's own jobs. Refused for anyone else's.
 */
export async function getEvalJob(jobArn: string, idToken: string): Promise<EvalJob> {
    const body = await apiRequest<JobResponse>(
        `/evaluations/status?jobArn=${encodeURIComponent(jobArn)}`,
        idToken,
    );
    return toJob(body);
}

/**
 * List the caller's recent evaluation jobs.
 */
export async function listEvalJobs(idToken: string): Promise<EvalJobSummary[]> {
    const { jobs } = await apiRequest<{ jobs: JobResponse[] }>("/evaluations", idToken);
    return jobs.map(toJob);
}

/**
 * Read a finished job's scores. Null until the output has been written.
 */
export async function getEvalResults(
    jobId: string,
    idToken: string,
): Promise<EvalResults | null> {
    const { results } = await apiRequest<{ results: EvalResults | null }>(
        `/evaluations/results?jobId=${encodeURIComponent(jobId)}`,
        idToken,
    );
    return results;
}
