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
                { id: "schedule", header: "Schedule", cell: (j) => j.schedule ? <code>{j.schedule}</code> : <Badge color="blue">One-time</Badge> },
                { id: "recipient", header: "To", cell: (j) => j.payload?.to?.replace("@s.whatsapp.net", "") || "—" },
                { id: "message", header: "Message", cell: (j) => j.payload?.message?.slice(0, 40) || "—" },
                { id: "channel", header: "Channel", cell: (j) => j.notify_channel || "—" },
                {
                    id: "actions",
                    header: "",
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
