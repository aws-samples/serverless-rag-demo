import * as React from "react";
import FileUpload from "@cloudscape-design/components/file-upload";
import FormField from "@cloudscape-design/components/form-field";
import Button from "@cloudscape-design/components/button";
import SpaceBetween from "@cloudscape-design/components/space-between";
import axios from "axios";

export function UploadUI() {
   const [value, setValue] = React.useState<File[]>([]);
   const upload_file = (files: any) => {
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
      <Button variant="primary" onClick={(event) => upload_file(event)}>Index Document</Button>
      <Button>Delete All</Button>
      </SpaceBetween>
      

      </FormField>
    );


}