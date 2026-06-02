import {
    Table,
    Header,
    Box,
    Badge,
    Button,
} from "@cloudscape-design/components";
import { CronJob } from "./types";

interface JobViewerProps {
    jobs: CronJob[];
    onDelete: (jobId: string) => void;
}

export function JobViewer({ jobs, onDelete }: JobViewerProps) {
    return (
        <Table
            header={<Header variant="h3">Scheduled Jobs</Header>}
            items={jobs}
            columnDefinitions={[
                { id: "name", header: "Name", cell: (j) => j.name },
                { id: "schedule", header: "Schedule", cell: (j) => <code>{j.schedule}</code> },
                { id: "agent", header: "Agent", cell: (j) => <Badge>{j.agent_id}</Badge> },
                { id: "action", header: "Action", cell: (j) => j.action },
                { id: "channel", header: "Notify Via", cell: (j) => j.notify_channel || "—" },
                {
                    id: "actions",
                    header: "Actions",
                    cell: (j) => (
                        <Button variant="icon" iconName="remove" onClick={() => onDelete(j.id)} />
                    ),
                },
            ]}
            empty={
                <Box textAlign="center" padding="l">
                    No scheduled jobs. Ask an agent to schedule something!
                </Box>
            }
        />
    );
}
