import * as React from "react";
import FileUpload from "@cloudscape-design/components/file-upload";
import FormField from "@cloudscape-design/components/form-field";
import Button from "@cloudscape-design/components/button";
import SpaceBetween from "@cloudscape-design/components/space-between";
import axios from "axios";
import config from '../../config.json'
import { StorageHelper } from "../../common/helpers/storage-helper";
import Flashbar from "@cloudscape-design/components/flashbar";
import Link from "@cloudscape-design/components/link";

export function UploadUI() {
  React.useEffect(() => {
    websocket_builder()
  })
  const [value, setValue] = React.useState<File[]>([]);
  const [showFlashbar, setShowFlashbar] = React.useState(false)
  const [items, setItems] = React.useState([
    {
      type: "info",
      dismissible: true,
      dismissLabel: "Dismiss message",
      onDismiss: () => setItems([]),
      content: (
        <>
        </>
      ),
      id: "message_1"
    }
  ]);
  var ws = null; 
  var connect_id = null;
  const socketUrl = config.indexingsocketUrl;
  
  function build_form_data(result, formdata) {
    if ('fields' in result) {
      for (var key in result['fields']) {
        formdata.append(key, result['fields'][key])
      }
    }
    return formdata
  }

  const delete_index = () => {

    axios.delete(config.apiUrl + 'index-documents', {
      headers: {
        authorization: StorageHelper.getAuthToken(),
        "Content-Type": "text/json",
      }
    }).then((result) => {
      console.log(result['data']['result'])
    }).catch((err) => {
      console.log(err)
    })

  }

  const websocket_builder = () => {
    if ("WebSocket" in window) {
        if(ws==null || ws.readyState==3 || ws.readyState==2) {          
          ws = new WebSocket(socketUrl);
          ws.onerror = function (event) {
            console.log(event);
          }
        }

        ws.onopen = () => {
          // Request for connect_id
          ws.send(JSON.stringify({ request: 'connect_id'}));
        };

        ws.onmessage = (event) => {
          var websocket_request = JSON.parse(event.data)
          if ('connect_id' in websocket_request) {
            connect_id = websocket_request['connect_id']
          } else if ('message' in websocket_request && 'statusCode' in websocket_request) {
            setItems([generate_flashbar_message(websocket_request['message'], false)])
          }
        };

        ws.onclose = () => {
          console.log('WebSocket connection closed');
          ws=null;
        };

      } else {
        console.log('WebSocket is not supported by your browser.');
        
      }
    }

  const generate_flashbar_message = (message: string, loading_state: boolean) => {
    return {
      type: "info",
      dismissible: true,
      loading: loading_state,
      dismissLabel: "Dismiss message",
      onDismiss: () => setItems([]),
      content: (
        <>
          {message}
        </>
      ),
      id: "message_1"
    }
  }

  const upload_file = () => {
    setItems([generate_flashbar_message('Uploading file to S3', true)])
    setShowFlashbar(true)
    for (var i = 0; i < value.length; i++) {
      // remove the words after the last dot
      var file_data = value[i]
      var file_name = file_data['name'];
      var period = file_name.lastIndexOf('.');
      var file_name_no_ext = file_name.substring(0, period);
      file_name_no_ext = file_name_no_ext.replace(/\s/g,'-')
      file_name_no_ext = file_name_no_ext.replace(/[^0-9a-z-]/gi, '')
      var fileExtension = file_name.substring(period + 1);
      axios.get(config.apiUrl + 'get-presigned-url', {
        params:{ "file_extension": fileExtension, "file_name": file_name_no_ext, "connect_id": connect_id }, 
        headers: {
          authorization: StorageHelper.getAuthToken(),
        }
      }) // Handle the response from backend here
        .then(function(result) {
          var formData = new FormData();
          formData = build_form_data(result['data']['result'], formData)
          formData.append('file', file_data);
          var upload_url = result['data']['result']['url']
          axios.post(upload_url, formData)
          .then(function(result) {
            setItems([generate_flashbar_message('File uploaded successfully', false)])
            // TODO:  Open a websocket listener here to listen on indexing status
          }).catch(function(err) {
            console.log(err)
            setItems([generate_flashbar_message('Error uploading file', false)])
          })
        // Catch errors if any
        .catch((err) => {
          console.log(err)
          setItems([generate_flashbar_message('Error generating presigned url', false)])
         });

    }).catch((err)=> {
      console.log(err)
    })
  }
}

  return (
    <FormField
      label="Form field label"
      description="Description"
    >
      { showFlashbar ? <Flashbar items={items}/> : null }
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
        <Button onClick={(event) => delete_index()} >Delete All</Button>
      </SpaceBetween>

    </FormField>
  );
}