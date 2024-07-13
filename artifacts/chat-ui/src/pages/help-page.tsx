import { HelpPanel, Icon } from "@cloudscape-design/components";
import { HelpPage } from "../common/types";
import config from "../help-properties.json";

export default function Help(props: HelpPage) {
    return (
        <HelpPanel
            header={<h2>{(config[props.setPageId])?config[props.setPageId].title: ""}</h2>}
        >
            <div dangerouslySetInnerHTML={{__html: (config[props.setPageId])?config[props.setPageId].description : ""}}>
            </div>
        </HelpPanel>
    );
}
