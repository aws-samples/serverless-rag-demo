import BaseAppLayout from "../components/base-app-layout";
import { UploadUI } from "../components/upload-ui/upload-ui";

export default function UploadPage() {

  return (
    <BaseAppLayout
      content={
        <UploadUI/>
      }
    />
  );
}
