import { useState } from "react";
import {FileUpload , FormField , Button , SpaceBetween}from "@cloudscape-design/components";
import axios from "axios";
import config from '../../config.json'
import { StorageHelper } from "../../common/helpers/storage-helper";

export function UploadUI() {
  const [value, setValue] = useState<File[]>([]);
  
  function build_form_data(result, formdata) {
    if ('fields' in result) {
      for (var key in result['fields']) {
        formdata.append(key, result['fields'][key])
      }
    }
    return formdata
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
      axios.get(config.apiUrl + '/rag/get-presigned-url', {
        params:{ "file_extension": fileExtension, "file_name": file_name_no_ext }, 
        headers: {
          authorization: StorageHelper.getAuthToken(),
        }
      }) // Handle the response from backend here
        .then(function(result){
          var formData = new FormData();
          formData = build_form_data(result['data']['result'], formData)
          formData.append('file', file_data);
          var upload_url = result['data']['result']['url']
          axios.post(upload_url, formData)
          .then(function(result) {
            console.log(result['data']['result']['s3_key'])
          })
        }).catch(function(err) {
            console.log(err)

        })
        // Catch errors if any
        .catch((err) => {
          console.log(err)
         });

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