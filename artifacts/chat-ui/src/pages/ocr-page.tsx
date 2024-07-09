import {
  Container,
  ContentLayout,
  Header,
  Button,
  Grid,
  SpaceBetween,
  Textarea,
} from "@cloudscape-design/components";
import { useState, useEffect, useContext } from "react";
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
  const inputFileRef = React.useRef(null);
  const fileDisplayRef = React.useRef(null);
  const [showHint, setShowHint] = useState(true);
  const [ocrOut, setOcrOut] = useState("");
  const appData = useContext(AppContext);
  
  useEffect(() => {
    const init = async () => {
      let userdata = await AuthHelper.getUserDetails();
      props.setAppData({
        userinfo: userdata
      })
    }
    init();
  },[])

  const select_file = () => {
    inputFileRef.current?.click();
  }

  const remove_file = (event) => {
    base64File = []
    const allImg = fileDisplayRef.current.querySelectorAll('object');
    allImg.forEach(item => item.remove());
    files = []
    fileDisplayRef.current.dataset.img = ''
    setShowHint(true)
  }

  const add_file = (event) => {
    const fileInput = event.target;
    files = fileInput.files;
    console.log(files);
    if (files.length > 0) {
      for (var i = 0; i < files.length; i++) {
        if (files[i].size < 50000000) {
          setShowHint(false)
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
          alert("File size must be less than 5MB");
        }
      }
    }
    //hack: Triggers a change even when same file is added again
    event.target.value=''
  }

  const base64ToArrayBuffer = (base64) =>  {
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
      let idToken = appData.userinfo.tokens.idToken.toString();
      for (var i = 0; i < base64File.length; i++) {
            var content = base64File[i]
            var file_extension = ''
            var file_type = content.substring("data:".length,  content.indexOf(";base64"))
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
                send_over_socket(unique_file_name + '.' + file_extension)
            })
            console.log("Uploaded successfully")
          }).catch(function (err) {
            console.log(err)
  
          })
          // Catch errors if any
          .catch((err) => {
            console.log(err)
          });
  
      }
    }

  }

  function send_over_socket(file_name) {
    if (ws == null || ws.readyState == 3 || ws.readyState == 2) {
      ws = new WebSocket(config.websocketUrl + "?access_token=" + sessionStorage.getItem('idToken'));
      ws.onerror = function (event) {
        console.log(event);
      };
    } else {
      // query_vectordb allowed values -> yes/no

      ws.send(JSON.stringify({
        query: JSON.stringify([{"role": "user", "content": [
          {"type": "document", "file_name": file_name},
          {"type": "text", "text": "extract the text from the given image"}]}]),
          behaviour: 'ocr',
          'query_vectordb': 'no',
          'model_id': 'anthropic.claude-3-haiku-20240307-v1:0'
          
      }));
      
    }

    ws.onopen = () => {
      ws.send(JSON.stringify({
        query: JSON.stringify([{"role": "user", "content": [
          {"type": "document", "file_name": file_name},
          {"type": "text", "text": "extract the text from the given image"}]}]),
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
          setOcrOut(msgs)
          msgs=null
        }
        
      } else {
        // Display errors
        setOcrOut(chat_output)
      }
    }

  }

    ws.onclose = () => {
      console.log('WebSocket connection closed');
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
      <Container
        fitHeight
      >
                <Grid gridDefinition={[
                  { colspan: { default: 6 } },
                  { colspan: { default: 1 } },
                  { colspan: { default: 5 } },
                ]}> 

                <div>
                  <div><input type="file" ref={inputFileRef} 
                        accept=".png, .jpg, .jpeg, .pdf"
                        hidden onChange={add_file}></input></div>
                       <div className={style.file_img_area} ref={fileDisplayRef} data-img=""></div>
                  
                      {showHint ? (
                          <>
                          <div>
                          <i className='bx bxs-cloud-upload icon'></i>
                          <h3>Supported file types:   pdf jpg png</h3>
                          <p>File size must be less than <span>5 MB</span></p>
                          </div>
                      
                          </>): null}
                  <div>
                      <Button iconAlign="right" variant="normal" onClick={select_file}>Select File</Button>
                      <Button iconAlign="right" variant="normal" onClick={remove_file}>Remove File</Button>
                      <Button iconAlign="right" variant="primary" onClick={perform_ocr}>Perform OCR</Button>
                  </div> 
                  </div>
                  
                  <div className={style.vertical_line}></div>
                  
                  <div>
                     <Textarea value={ocrOut} placeholder="OCR Output" readOnly={true} rows={10}></Textarea>

                  </div>
              </Grid>
              {/* Image viewer component ends */}

      </Container>
    </ContentLayout>
  );
}


export default withAuthenticator(OcrPage)