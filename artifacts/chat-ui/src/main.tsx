import ReactDOM from "react-dom/client";
import { StorageHelper } from "./common/helpers/storage-helper";
import App from "./app";
import { Amplify } from 'aws-amplify';
import { loadRuntimeConfig } from "./runtime-config";
import "@cloudscape-design/global-styles/index.css";


async function init() {
  const config = await loadRuntimeConfig();

  Amplify.configure({
    "aws_project_region": config.cognitoRegion,
    "aws_cognito_region": config.cognitoRegion,
    "aws_user_pools_id": config.cognitoUserPoolId,
    "aws_user_pools_web_client_id": config.cognitoClientId,
  });

  const root = ReactDOM.createRoot(
    document.getElementById("root") as HTMLElement
  );

  const theme = StorageHelper.getTheme();
  StorageHelper.applyTheme(theme);

  root.render(
      <App />
  );
}

init();
