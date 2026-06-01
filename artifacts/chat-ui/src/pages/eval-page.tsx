import { useState, useContext, useEffect } from "react";
import {
    ContentLayout, Header, SpaceBetween, Container,
    Table, StatusIndicator, Button, Box,
} from "@cloudscape-design/components";
import { withAuthenticator } from "@aws-amplify/ui-react";
import { AppContext } from "../common/context";
import { AuthHelper } from "../common/helpers/auth-help";
import { AppPage } from "../common/types";
import { EvalInput } from "../components/eval-ui/eval-input";
import { EvalDashboard } from "../components/eval-ui/eval-dashboard";
import {
    EvalQuestion, EvalResults, EvalJobSummary,
    uploadEvalDataset, createEvalJob, getEvalJob,
    getEvalResults, listEvalJobs,
} from "../common/evaluation-service";
import { getRuntimeConfig } from "../runtime-config";

function EvalPageContent(props: AppPage) {
    const appData = useContext(AppContext);
    const [isRunning, setIsRunning] = useState(false);
    const [results, setResults] = useState<EvalResults | null>(null);
    const [recentJobs, setRecentJobs] = useState<EvalJobSummary[]>([]);
    const [error, setError] = useState("");

    useEffect(() => {
        const init = async () => {
            let userdata = await AuthHelper.getUserDetails();
            props.setAppData({ userinfo: userdata });
        };
        init();
    }, []);

    const getIdToken = (): string =>
        appData.userinfo?.tokens?.idToken?.toString() || "";

    const getUserEmail = (): string =>
        appData.userinfo?.signInDetails?.loginId || appData.userinfo?.username || "";

    const refreshJobs = async () => {
        try {
            const jobs = await listEvalJobs(getIdToken());
            setRecentJobs(jobs);
        } catch { /* ignore */ }
    };

    useEffect(() => {
        if (appData.userinfo) refreshJobs();
    }, [appData]);

    const handleStartEvaluation = async (questions: EvalQuestion[], metrics: string[]) => {
        setIsRunning(true);
        setResults(null);
        setError("");

        const idToken = getIdToken();
        const userEmail = getUserEmail();
        const jobId = crypto.randomUUID();
        const jobName = `srd-eval-${Date.now()}`;

        try {
            const datasetUri = await uploadEvalDataset(questions, jobId, userEmail, idToken);
            const config = getRuntimeConfig();
            const outputPrefix = `s3://${config.dataBucketName}/evaluations/${userEmail}/${jobId}/output/`;

            const jobArn = await createEvalJob(jobName, datasetUri, outputPrefix, metrics, idToken);

            const pollInterval = setInterval(async () => {
                try {
                    const job = await getEvalJob(jobArn, idToken);
                    if (job.status === "Completed") {
                        clearInterval(pollInterval);
                        const evalResults = await getEvalResults(userEmail, jobId, idToken);
                        setResults(evalResults);
                        setIsRunning(false);
                        refreshJobs();
                    } else if (job.status === "Failed" || job.status === "Stopped") {
                        clearInterval(pollInterval);
                        setError(`Evaluation ${job.status.toLowerCase()}`);
                        setIsRunning(false);
                        refreshJobs();
                    }
                } catch (err: any) {
                    clearInterval(pollInterval);
                    setError(`Polling error: ${err.message}`);
                    setIsRunning(false);
                }
            }, 15000);

            setTimeout(() => {
                clearInterval(pollInterval);
                setIsRunning((running) => {
                    if (running) {
                        setError("Evaluation is still running. Check back later in Recent Evaluations.");
                        refreshJobs();
                    }
                    return false;
                });
            }, 600000);

        } catch (err: any) {
            setError(`Failed to start evaluation: ${err.message}`);
            setIsRunning(false);
        }
    };

    return (
        <ContentLayout header={<Header variant="h1">RAG Evaluation</Header>}>
            <SpaceBetween size="l">
                {error && (
                    <Container>
                        <StatusIndicator type="error">{error}</StatusIndicator>
                    </Container>
                )}

                <EvalInput onStartEvaluation={handleStartEvaluation} isRunning={isRunning} />
                <EvalDashboard results={results} isLoading={isRunning} />

                <Container header={
                    <Header variant="h2" actions={<Button iconName="refresh" onClick={refreshJobs}>Refresh</Button>}>
                        Recent Evaluations
                    </Header>
                }>
                    <Table
                        items={recentJobs}
                        columnDefinitions={[
                            { id: "name", header: "Job Name", cell: (item) => item.jobName },
                            {
                                id: "status", header: "Status", cell: (item) => {
                                    const type = item.status === "Completed" ? "success"
                                        : item.status === "InProgress" ? "loading"
                                        : item.status === "Failed" ? "error" : "info";
                                    return <StatusIndicator type={type}>{item.status}</StatusIndicator>;
                                }
                            },
                            { id: "created", header: "Created", cell: (item) => new Date(item.createdAt).toLocaleString() },
                        ]}
                        empty={<Box textAlign="center" color="text-body-secondary">No evaluations yet</Box>}
                        stripedRows
                    />
                </Container>
            </SpaceBetween>
        </ContentLayout>
    );
}

export default withAuthenticator(EvalPageContent);
