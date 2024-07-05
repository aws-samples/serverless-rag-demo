import ReactDOM from "react-dom/client";
import { StorageHelper } from "./common/helpers/storage-helper";
import App from "./app";
import { Amplify } from 'aws-amplify';
import config from "./config.json";
import "@cloudscape-design/global-styles/index.css";


Amplify.configure({
  "aws_project_region": config.region,
  "aws_cognito_region": config.region,
  "aws_user_pools_id": config.userPoolId,
  "aws_user_pools_web_client_id": config.clientId,
});

const root = ReactDOM.createRoot(
  document.getElementById("root") as HTMLElement
);

const theme = StorageHelper.getTheme();
StorageHelper.applyTheme(theme);

root.render(
    <App />
);
