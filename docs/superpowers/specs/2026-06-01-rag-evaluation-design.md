# RAG Evaluation Feature Design

**Goal:** Add a dedicated Evaluation page to the UI that lets users assess RAG quality using Bedrock Evals, with both reference-free and ground-truth modes, plus lightweight thumbs up/down feedback on chat responses.

**Architecture:** Browser calls Bedrock evaluation APIs directly via Identity Pool credentials (no backend needed). Evaluation datasets and results stored in the existing S3 data bucket under `evaluations/` prefix. Chat feedback stored as daily JSONL files under `feedback/` prefix.

**Tech Stack:** Bedrock Evaluation Jobs API, S3 (existing data bucket), Cognito Identity Pool (existing), Cloudscape UI components.

---

## 1. Evaluation Page (New Top-Level Tab)

A new page alongside "Document Chat" and "Multi-Agent" with two mode cards:

### Reference-Free Mode
- User provides questions only (no expected answers)
- Input methods:
  - Manual entry: type questions one by one or paste multiple (one per line)
  - File upload: JSON array of `[{"question": "..."}]`
- Bedrock evaluates retrieval + generation quality without ground truth
- Uses LLM-as-judge (Claude Sonnet) to score responses

### Ground Truth Mode
- User uploads JSON file with Q&A pairs:
  ```json
  [
    {"question": "What is the join process?", "expected_answer": "Submit application, receive email confirmation..."},
    {"question": "How do I claim?", "expected_answer": "Log into member portal, select Claims..."}
  ]
  ```
- Optional `context` field for expected source context
- Bedrock compares KB-generated answers against expected answers

## 2. Metrics

User selects which metrics to evaluate via checkboxes.

**Retrieval + Generation (default):**
- Correctness — is the answer factually correct?
- Completeness — does it cover all relevant information?
- Helpfulness — is it useful to the user?
- LogicalCoherence — is the reasoning sound?
- Faithfulness — is it grounded in retrieved context (no hallucination)?

**Retrieval Only:**
- ContextRelevance — are retrieved chunks relevant to the query?
- ContextCoverage — do retrieved chunks cover what's needed to answer?

Default selection: Faithfulness, Correctness, Completeness (most useful for RAG quality assessment).

## 3. Evaluation Flow

1. User selects mode (reference-free or ground truth)
2. User provides questions (manual entry or file upload)
3. User selects metrics (checkboxes, sensible defaults pre-checked)
4. User clicks "Run Evaluation"
5. UI writes input dataset as JSONL to `s3://data-bucket/evaluations/{userEmail}/{jobId}/input.jsonl`
6. UI calls `bedrock:CreateEvaluationJob` with:
   - `applicationType: "RagEvaluation"`
   - `evaluationConfig` with selected metrics
   - `inferenceConfig.ragConfigs.knowledgeBaseConfig.retrieveAndGenerateConfig` pointing to our KB
   - `outputDataConfig` pointing to `s3://data-bucket/evaluations/{userEmail}/{jobId}/output/`
   - Evaluator model: `anthropic.claude-sonnet-4-6-v1:0` (us-east-1)
7. UI polls `bedrock:GetEvaluationJob` every 15 seconds
8. When complete, UI reads results from S3 output path
9. Results displayed in dashboard

## 4. Results Dashboard

**Aggregate scores (top row):**
- One card per metric showing score 0.0–1.0
- Color coding: green (>0.8), yellow (0.6–0.8), red (<0.6)

**Per-question breakdown (below):**
- Expandable table with columns: Question, Generated Answer, Score per metric
- Sortable by any metric score (find weakest answers)
- Click to expand shows full answer + retrieved sources

**Recent evaluations list:**
- Shows past evaluation jobs via `ListEvaluationJobs`
- Status indicator: In Progress / Completed / Failed
- Click to view results of any past evaluation

## 5. Thumbs Up/Down on Chat Messages

**UI addition to `chat-ui-message.tsx`:**
- Small thumbs-up and thumbs-down icon buttons on each AI response
- Clicking one highlights it (toggle state) and writes feedback

**Storage:**
- Append to `s3://data-bucket/feedback/{YYYY-MM-DD}.jsonl`
- Each line:
  ```json
  {"timestamp": "2026-06-01T10:30:00Z", "userEmail": "user@example.com", "question": "What is...", "answer": "Based on...", "sources": ["s3://bucket/key"], "rating": "up"}
  ```
- Fire-and-forget: don't block chat UX, silent fail with one retry

**Future use:** Accumulated feedback can be exported as ground-truth eval input.

## 6. IAM Permissions

**Additions to Cognito authenticated role:**
```
bedrock:CreateEvaluationJob
bedrock:GetEvaluationJob
bedrock:ListEvaluationJobs
```

**S3 access (extend existing policy):**
```
s3:PutObject on s3://data-bucket/evaluations/*
s3:GetObject on s3://data-bucket/evaluations/*
s3:PutObject on s3://data-bucket/feedback/*
```

**New Bedrock evaluation service role (CDK):**
- Allows Bedrock eval service to:
  - Read from the Knowledge Base (`bedrock:Retrieve`, `bedrock:RetrieveAndGenerate`)
  - Read input dataset from S3 (`s3:GetObject` on `evaluations/*/input.jsonl`)
  - Write results to S3 (`s3:PutObject` on `evaluations/*/output/*`)
  - Invoke evaluator model (`bedrock:InvokeModel` on Claude Sonnet)

## 7. Data Format (Bedrock JSONL)

**Input JSONL for ground-truth mode:**
```jsonl
{"conversationTurnContent": {"prompt": {"content": [{"text": "What is the GU Health join process?"}]}, "referenceResponse": {"content": [{"text": "Submit application online, receive email confirmation, get welcome pack, log into member portal."}]}}}
```

**Input JSONL for reference-free mode:**
```jsonl
{"conversationTurnContent": {"prompt": {"content": [{"text": "What is the GU Health join process?"}]}}}
```

## 8. Error Handling

- **Job timeout:** Poll for max 10 minutes, then show "still running" with job ID and option to check later
- **Empty KB:** Warning before starting if no documents indexed
- **Feedback write failure:** Silent fail, retry once, don't interrupt chat
- **Concurrent evals:** One active job per user; disable "Run" button while in progress
- **Job failure:** Show error message from Bedrock with retry option

## 9. File Structure (New/Modified)

- `src/pages/eval-page.tsx` — new evaluation page
- `src/components/eval-ui/eval-dashboard.tsx` — results dashboard
- `src/components/eval-ui/eval-input.tsx` — question input (manual + file upload)
- `src/common/evaluation-service.ts` — Bedrock eval API calls + S3 dataset/results I/O
- `src/common/feedback-service.ts` — thumbs up/down feedback writer
- `src/components/chat-ui/chat-ui-message.tsx` — add thumbs up/down buttons
- `infrastructure/cognito_stack.py` — add eval IAM permissions
- CDK: new IAM role for Bedrock evaluation service

## 10. Out of Scope (Future)

- Precision and recall metrics (deferred per user request)
- Automated scheduled evaluations
- Feedback-to-ground-truth conversion UI
- Custom metric definitions
- Evaluation comparison (diff two eval runs)
