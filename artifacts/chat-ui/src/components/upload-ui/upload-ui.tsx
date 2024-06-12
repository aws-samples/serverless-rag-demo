import * as React from "react";
import FileUpload from "@cloudscape-design/components/file-upload";
import FormField from "@cloudscape-design/components/form-field";
import Button from "@cloudscape-design/components/button";
import SpaceBetween from "@cloudscape-design/components/space-between";
import axios from "axios";
interface UploadUIInputPanelProps {
  upload_file?: (files: File[]) => void;
}

export function UploadUI( props: UploadUIInputPanelProps ) {
   const [value, setValue] = React.useState([]);
   const upload_file = (files:File[]) => {
      console.log(files)
      axios.post('XXXXXXXXXXXXXXXXXXXXXXXXXXXX', {
         file: value
      })
      .then(function (response) {
         console.log(response);
      })
      .catch(function (error) {
         console.log(error);
      });
   }

   return (
      <FormField
        label="Form field label"
        description="Description"
      >
      <FileUpload
          onChange={({ detail }) => {
            setValue(detail.value);
            upload_file(detail)
          }}
          value={value}
          i18nStrings={{
            uploadButtonText: e =>
              e ? "Choose files" : "Choose file",
            dropzoneText: e =>
              e
                ? "Drop files to upload"
                : "Drop file to upload",
            removeFileAriaLabel: e =>
              `Remove file ${e + 1}`,
            limitShowFewer: "Show fewer files",
            limitShowMore: "Show more files",
            errorIconAriaLabel: "Error"
          }}
          showFileLastModified
          showFileSize
          showFileThumbnail
          tokenLimit={3}
          constraintText="Hint text for file requirements"
      />
      <br/><br/><br/><br/><br/><br/><br/><br/><br/>
      <SpaceBetween direction="horizontal" size="xs">
      <Button variant="primary" onClick={upload_file}>Index Document</Button>
      <Button>Delete All</Button>
      </SpaceBetween>
      

      </FormField>
    );


}