import {
  Container,
  ContentLayout,
  Header,
  Button,
  ColumnLayout,
  SpaceBetween,
  Textarea,Alert, Box, Spinner
} from "@cloudscape-design/components";
import { useState, useEffect, useContext, useRef } from "react";
import { withAuthenticator, useAuthenticator } from '@aws-amplify/ui-react';
import { AppPage } from "../common/types";
import { AuthHelper } from "../common/helpers/auth-help";
import React from "react";
import style from "../styles/ocr-page.module.scss";
import axios from "axios";
import config from "../config.json";
import { AppContext } from "../common/context";

var base64File = []
var files = []
var msgs = null
var ws = null
function OcrPage(props: AppPage) {
  const inputFileRef = useRef(null);
  const fileDisplayRef = useRef(null);
  const [is_disabled, setDisabled] = useState(false);
  const [performOcrDisabled, setPerformOCRDisabled] = useState(true)
  const [showHint, setShowHint] = useState(true);
  const [ocrOut, setOcrOut] = useState("");
  const appData = useContext(AppContext);
  const [isRunning, setRunning] = useState(false);
  const [showAlert, setShowAlert] = useState(false)
  const [alertMsg, setAlertMsg] = useState("")
  const [alertType, setAlertType] = useState("error")

  useEffect(() => {
    const init = async () => {
      let userdata = await AuthHelper.getUserDetails();
      props.setAppData({
        userinfo: userdata
      })
    }
    init();
  }, [])

  const select_file = () => {
    inputFileRef.current?.click();
  }

  const remove_file = (event) => {
    setPerformOCRDisabled(true)
    base64File = []
    const allImg = fileDisplayRef.current.querySelectorAll('object');
    allImg.forEach(item => item.remove());
    files = []
    fileDisplayRef.current.dataset.img = ''
    setShowHint(true)
    setOcrOut("")
  }

  const add_file = (event) => {
    const fileInput = event.target;
    files = fileInput.files;
    console.log(files);
    setShowHint(false)
    if (files.length > 0) {
      for (var i = 0; i < files.length; i++) {
        if (files[i].size < 10000000) {
          setPerformOCRDisabled(false)
          var reader = new FileReader();
          reader.onload = function (e) {
            const imgUrl = reader.result;
            base64File.push(e.target.result)
            const img = document.createElement('object');
            img.data = imgUrl;
            fileDisplayRef.current.appendChild(img);
            fileDisplayRef.current.classList.add('active');
          };
          reader.readAsDataURL(files[i]);
        } else {
            setAlertMsg("File size must be less than 10MB");
            setAlertType("error")
            setShowAlert(true)
        }
      }
    }
    //hack: Triggers a change even when same file is added again
    event.target.value = ''
  }

  const base64ToArrayBuffer = (base64) => {
    var binaryString = atob(base64);
    var bytes = new Uint8Array(binaryString.length);
    for (var i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    // return bytes.buffer;
    return new File([bytes], 'sample')
  }


  const perform_ocr = () => {
    if ("WebSocket" in window) {
      setRunning(true)
      setDisabled(true)
      setPerformOCRDisabled(true)
      let idToken = appData.userinfo.tokens.idToken.toString();
      for (var i = 0; i < base64File.length; i++) {
        var content = base64File[i]
        var file_extension = ''
        var file_type = content.substring("data:".length, content.indexOf(";base64"))
        if (file_type.includes('/')) {
          file_extension = file_type.split('/')[1]
        } else {
          file_extension = file_type
        }
        var content = content.replace(/^data:.+;base64,/, "")
        var file_bytes = base64ToArrayBuffer(content)

        var unique_file_name = crypto.randomUUID()
        axios.get(config.apiUrl + 'get-presigned-url', {
          params: { "file_extension": file_extension, "file_name": unique_file_name, "type": "ocr" },
          headers: {
            authorization: appData.userinfo.tokens.idToken.toString()
          }
        }) // Handle the response from backend here
          .then(function (result) {
            var formData = new FormData();
            formData = build_form_data(result['data']['result'], formData)
            formData.append('file', file_bytes);

            var upload_url = result['data']['result']['url']
            axios.post(upload_url, formData).then(function (result) {
              setOcrOut("")
              msgs = null
              setShowAlert(true)
              setAlertMsg("File uploaded successfully. Extracting text from document")
              setAlertType("info")
              send_over_socket(unique_file_name + '.' + file_extension)
              
            })
            console.log("Uploaded successfully")
          }).catch(function (err) {
            console.log(err)
            setRunning(false)
            setDisabled(false)
            setPerformOCRDisabled(false)

          })
          // Catch errors if any
          .catch((err) => {
            console.log(err)
            setRunning(false)
            setDisabled(false)
            setPerformOCRDisabled(false)
          });

      }
    }

  }

  function send_over_socket(file_name) {
    if (ws == null || ws.readyState == 3 || ws.readyState == 2) {
      var idToken = appData.userinfo.tokens.idToken.toString()
      ws = new WebSocket(config.websocketUrl + "?access_token=" + idToken);
      
      ws.onerror = function (event) {
        console.log(event);
        setDisabled(false);
        setRunning(false);
        setPerformOCRDisabled(false)
      };
    } else {
      // query_vectordb allowed values -> yes/no

      ws.send(JSON.stringify({
        query: JSON.stringify([{
          "role": "user", "content": [
            { "type": "document", "file_name": file_name },
            { "type": "text", "text": "extract the text from the given image" }]
        }]),
        behaviour: 'ocr',
        'query_vectordb': 'no',
        'model_id': 'anthropic.claude-3-haiku-20240307-v1:0'

      }));

    }

    ws.onopen = () => {
      ws.send(JSON.stringify({
        query: JSON.stringify([{
          "role": "user", "content": [
            { "type": "document", "file_name": file_name },
            { "type": "text", "text": "extract the text from the given image" }]
        }]),
        behaviour: 'ocr',
        'query_vectordb': 'no',
        'model_id': 'anthropic.claude-3-haiku-20240307-v1:0'

      }));
    };


    ws.onmessage = (event) => {
      if (event.data.includes('message')) {
        var evt_json = JSON.parse(event.data);
        setOcrOut(ocrOut + evt_json['message'])
      }
      else {
        var chat_output = JSON.parse(atob(event.data));
        if ('text' in chat_output) {
          if (msgs) {
            msgs += chat_output['text'];
          } else {
            msgs = chat_output['text'];
          }

          if (msgs.endsWith('ack-end-of-msg')) {
            msgs = msgs.replace('ack-end-of-msg', '');
            var out_message = ocrOut + msgs
            setOcrOut(out_message)
            setDisabled(false);
            setRunning(false);
            setPerformOCRDisabled(false)
          }

        } else {
          if (msgs) {
            msgs += chat_output
          } else {
            msgs = chat_output
          }
          var out_message = ocrOut + msgs
          setOcrOut(out_message)
        }
      }

    }

    ws.onclose = () => {
      console.log('WebSocket connection closed');
      setRunning(false)
      setDisabled(false)
      setPerformOCRDisabled(false)
    };

    ws.onerror = function (event) {
      console.log(event);
      setDisabled(false);
      setRunning(false);
      setPerformOCRDisabled(false)
    };
  }


  function build_form_data(result, formdata) {
    if ('fields' in result) {
      for (var key in result['fields']) {
        formdata.append(key, result['fields'][key])
      }
    }
    return formdata
  }

  return (
    <ContentLayout
      defaultPadding
      headerVariant="high-contrast"
      header={
        <Header
          variant="h1"
          description="App description will come here"
        >
          OCR
        </Header>
      }
    >
      {(showAlert && alertType=='error') ? <Alert dismissible statusIconAriaLabel="Error" type='error' onDismiss={() => setShowAlert(false)}>{alertMsg}</Alert> : ""}
      {(showAlert && alertType=='success') ? <Alert dismissible statusIconAriaLabel="Success" type='success' onDismiss={() => setShowAlert(false)}>{alertMsg}</Alert> : ""}
      {(showAlert && alertType=='warning') ? <Alert dismissible statusIconAriaLabel="Warning" type='warning' onDismiss={() => setShowAlert(false)}>{alertMsg}</Alert> : ""}
      {(showAlert && alertType=='info') ? <Alert dismissible statusIconAriaLabel="Info" type='info' onDismiss={() => setShowAlert(false)}>{alertMsg}</Alert> : ""}
      <Container
        fitHeight
      >
        <Container variant="embed" fitHeight header={
          <Header
            variant="h3"
            actions={
              <SpaceBetween size="s" direction="horizontal">
                <input type="file" ref={inputFileRef} accept=".png, .jpg, .jpeg, .pdf" hidden onChange={add_file}></input>
                <Button iconAlign="right" disabled={is_disabled} variant="normal" onClick={select_file}>Select File</Button>
                <Button iconAlign="right" disabled={is_disabled} variant="normal" onClick={remove_file}>Remove File</Button>
                <Button iconAlign="right" disabled={performOcrDisabled}  variant="primary" onClick={perform_ocr}>{isRunning ? (
                <>
                  Loading&nbsp;
                  <Spinner />
                </>
              ) : (
                <>{"Perform OCR"}</>
              )}
              </Button>
                
              </SpaceBetween>
            }
          >
            Upload Document
          </Header>
        }
        >
          <SpaceBetween size="s">
          <ColumnLayout columns={2} variant="text-grid">
            <div className={style.file_img_area} ref={fileDisplayRef} data-img=""></div>
            <Textarea value={ocrOut} placeholder="OCR Output" readOnly={true} rows={10}></Textarea>
          </ColumnLayout>
          <Alert statusIconAriaLabel="Info" visible={showHint}> 
          <Box>
          <h3>Supported file types: pdf | jpg | png</h3>
          <p>File size must be less than <span>5 MB</span></p>
          </Box>
          </Alert>
          </SpaceBetween>
        </Container>
      </Container>
    </ContentLayout>
  );
}


export default withAuthenticator(OcrPage)