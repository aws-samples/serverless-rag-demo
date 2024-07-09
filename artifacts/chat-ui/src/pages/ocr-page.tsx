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
    base64File = []
    fileDisplayRef.current.dataset.img = ''
    setShowHint(true)
  }

  const add_file = (event) => {
    const fileInput = event.target;
    const files = fileInput.files;
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

  const perform_ocr = () => {
    var user_content = []
    // Only 5 MB file we can transmit over the API-GW
    let idToken = appData.userinfo.tokens.idToken.toString();
    if (base64File.length > 0) {
      var unique_id = crypto.randomUUID()
      for (var i = 0; i < base64File.length; i++) {
        axios.post(
          config.apiUrl + 'file_data',
          { "content": base64File[i], "id": unique_id },
          { headers: { authorization: "Bearer " + idToken } }
        ).then((result) => {
          console.log('Upload successful')
          var file_extension = result['data']['result']['file_extension']
          var file_id = result['data']['result']['file_id']
          var media_type = ""
          if (file_extension == 'pdf') {
            media_type="application/pdf"
          } else {
            media_type = 'image/' + file_extension
          }
          var partial_s3_key = file_id + '.' + file_extension
          user_content.push({ "type": "image", "source": { "type": "base64", "media_type": media_type, "file_extension": file_extension, "partial_s3_key": partial_s3_key } })
          if (i >= base64File.length - 1) {
              user_content.push({ "type": "text", "text": "Extract the text from the given document" })
          }
        })
      }
      


    }
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