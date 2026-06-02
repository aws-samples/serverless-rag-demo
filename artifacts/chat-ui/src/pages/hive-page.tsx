import { useEffect } from "react";
import { withAuthenticator } from "@aws-amplify/ui-react";
import { ContentLayout, Header } from "@cloudscape-design/components";
import { AuthHelper } from "../common/helpers/auth-help";
import { AppPage } from "../common/types";
import { HiveLayout } from "../components/hive/hive-layout";

function HivePage(props: AppPage) {
    useEffect(() => {
        const init = async () => {
            const userdata = await AuthHelper.getUserDetails();
            props.setAppData({ userinfo: userdata });
        };
        init();
    }, []);

    return (
        <ContentLayout
            defaultPadding
            headerVariant="high-contrast"
            header={
                <Header
                    variant="h1"
                    description="Your personal AI agent swarm with channels, tools, and autonomous capabilities"
                >
                    Hive
                </Header>
            }
        >
            <HiveLayout />
        </ContentLayout>
    );
}

export default withAuthenticator(HivePage);
