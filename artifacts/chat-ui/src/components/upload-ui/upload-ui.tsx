import * as React from "react";
import FileUpload from "@cloudscape-design/components/file-upload";
import FormField from "@cloudscape-design/components/form-field";
import Button from "@cloudscape-design/components/button";
import SpaceBetween from "@cloudscape-design/components/space-between";
import axios from "axios";
import config from '../../config.json'
import { StorageHelper } from "../../common/helpers/storage-helper";

export function UploadUI() {
  const [value, setValue] = React.useState<File[]>([]);
  const [base64Files, setBase64] = React.useState<String[]>([]);
  
  function build_form_data(result, formdata) {
    if ('fields' in result) {
      for (var key in result['fields']) {
        formdata.append(key, result['fields'][key])
      }
    }
    return formdata
  }

  function getBase64(files: File[]) {
    const base64s = []
    var reader = new FileReader();
    reader.onload = function () {
      base64s.push(reader.result)
      setBase64(base64s)
    };
    reader.onerror = function (error) {
      console.log('Error: ', error);
    };
    for(var i=0; i<files.length; i++) {
      reader.readAsDataURL(files[i]);
    }
  }

  function base64ToArrayBuffer(base64) {
    var binaryString = atob(base64);
    var bytes = new Uint8Array(binaryString.length);
    for (var i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    // return bytes.buffer;
    return new File([bytes], 'sample')
  }

  const upload_file = (files: any) => {
    console.log(files)
    for (var i = 0; i < value.length; i++) {
      // remove the words after the last dot
      var file_data = value[i]
      var file_name = file_data['name'];
      var period = file_name.lastIndexOf('.');
      var file_name_no_ext = file_name.substring(0, period);
      var fileExtension = file_name.substring(period + 1);
      axios({
        url: config.apiUrl + '/rag/get-presigned-url',
        method: "GET",
        headers: {
          authorization: StorageHelper.getAuthToken(),
        },
        data: { "file_extension": fileExtension, "file_name": file_name_no_ext },
      }) // Handle the response from backend here
        .then((result) => {
          var formData = new FormData();
          formData = build_form_data(result['result'], formData)
          var file_bytes = base64ToArrayBuffer(file_data)
          formData.append('file', file_bytes);
        })
        // Catch errors if any
        .catch((err) => { });

    }
  }

  return (
    <FormField
      label="Form field label"
      description="Description"
    >
      <FileUpload
        onChange={({ detail }) => {
          setValue(detail.value);
          getBase64(detail.value);
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
      <br /><br /><br /><br /><br /><br /><br /><br /><br />
      <SpaceBetween direction="horizontal" size="xs">
        <Button variant="primary" onClick={(event) => upload_file(event)}>Index Document</Button>
        <Button>Delete All</Button>
      </SpaceBetween>


    </FormField>
  );


}