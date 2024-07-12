import { useContext, useEffect, useState } from "react";
import { FileUpload, Button, SpaceBetween, Container, Header, Modal, Box, Table } from "@cloudscape-design/components";
import timeago from 'epoch-timeago';
import { LoadingBar } from "@cloudscape-design/chat-components";
import axios from "axios";
import config from '../../config.json'
import { AppContext } from "../../common/context";

export interface UploadDocProps {
  running?: boolean;
  notify_parent?: (message: string, notify_type: string) => void;
}
export function UploadUI(props: UploadDocProps) {
  const [value, setValue] = useState<File[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [userFiles, setUserFiles] = useState([]);
  const appData = useContext(AppContext);

  const refreshUserFileList = () => {
    setIsLoading(true);
    axios.get(`${config.apiUrl}get-indexed-files-by-user`, { headers: { authorization: appData.userinfo.tokens.idToken.toString() } })
      .then((result) => {
        setUserFiles(result.data.result)
        setIsLoading(false);
      })
  }
  useEffect(() => {
    if (appData.userinfo) {
      refreshUserFileList()
    }
  }, [appData])

  function build_form_data(result, formdata) {
    if ('fields' in result) {
      for (var key in result['fields']) {
        formdata.append(key, result['fields'][key])
      }
    }
    return formdata
  }

  const notify = (message, notify_type) => {
    props.notify_parent?.(message, notify_type);
  }

  const upload_file = (files: any) => {
    setIsLoading(true);
    setIsModalVisible(false);
    for (var i = 0; i < value.length; i++) {
      // remove the words after the last dot
      var file_data = value[i]
      var file_name = file_data['name'];
      var period = file_name.lastIndexOf('.');
      var file_name_no_ext = file_name.substring(0, period);
      var fileExtension = file_name.substring(period + 1);
      axios.get(config.apiUrl + 'get-presigned-url', {
        params: { "file_extension": fileExtension, "file_name": file_name_no_ext },
        headers: {
          authorization: appData.userinfo.tokens.idToken.toString()
        }
      }) // Handle the response from backend here
        .then(function (result) {
          var formData = new FormData();
          formData = build_form_data(result['data']['result'], formData)
          formData.append('file', file_data);
          var upload_url = result['data']['result']['url']
          axios.post(upload_url, formData)
            .then(function (result) {
              setIsModalVisible(false)
              notify("File uploaded successfully", "info")
              closeModalandRefresh();
            })
        }).catch(function (err) {
          console.log(err)
          notify("File not uploaded " + err, "error")
          setIsModalVisible(false)

        })
        // Catch errors if any
        .catch((err) => {
          console.log(err)
          notify("File not uploaded " + err, "error")
          setIsModalVisible(false)
        });

    }
  }

  const closeModalandRefresh = () => {
    setValue([]);
    setIsModalVisible(false);
    setIsLoading(true)
    setTimeout(() => {
      refreshUserFileList();
      setIsLoading(false)
    }, 5000)

  }

  const deleteByKey = (keyid) => {
    if (confirm(`Are you sure to delete ${keyid}`)) {
      setIsLoading(true);
      axios.post(`${config.apiUrl}del-file`, JSON.stringify({ s3_key: keyid }), { headers: { authorization: `Bearer ${appData.userinfo.tokens.idToken.toString()}` } })
        .then((result) => {
          notify('File was successfully deleted', 'info');
          setTimeout(() => {
            refreshUserFileList();
            setIsLoading(false);
          }, 5000)

        })
        .catch((err) => {
          notify('File was not deleted ' + err, 'error');
          console.log(err)
          refreshUserFileList()
          setIsLoading(false);
        })
    }
  }

  const deleteIndex = () => {
    if (confirm(`Are you sure to delete all your indexed data`)) {
      setIsLoading(true);
      axios.delete(`${config.apiUrl}index-documents`, 
      { headers: { authorization: `Bearer ${appData.userinfo.tokens.idToken.toString()}` } })
          .then((result) => {
            notify('Index deleted successfully ', 'info');
            setTimeout(() => {
              refreshUserFileList();
              setIsLoading(false);
            }, 5000)
  
          })
          .catch((err) => {
            console.log(err)
            notify('Index not deleted ' + err, 'error');
            refreshUserFileList()
            setIsLoading(false);
          })
    }
  }

  return (
    <Container
      fitHeight
      variant="embed"
      header={<Header
        actions={
          <SpaceBetween direction="horizontal" size="s">
            <Button iconName="refresh" onClick={() => refreshUserFileList()} disabled={isLoading}>Refesh</Button>
            <Button onClick={() => setIsModalVisible(true)} disabled={isLoading}>Upload File</Button>
            <Button onClick={() => deleteIndex()}variant="primary" iconName="delete-marker" disabled={isLoading}>Delete Index</Button>
          </SpaceBetween>

        }
        variant="h2">Upload you documents to index</Header>}
    >
      {isLoading && <LoadingBar variant="gen-ai" />}
      <Table
        variant="full-page"
        renderAriaLive={({
          firstIndex,
          lastIndex,
          totalItemsCount
        }) =>
          `Displaying items ${firstIndex} to ${lastIndex} of ${totalItemsCount}`
        }
        columnDefinitions={[
          {
            id: "file_id",
            header: "File Name",
            cell: item => item.file_id || "-",
            sortingField: "file_id",
            isRowHeader: true
          },
          {
            id: "file_index_status",
            header: "Index Status",
            cell: item => item.file_index_status || "-",
            sortingField: "file_index_status",
            isRowHeader: true
          },
          {
            id: "update_epoch",
            header: "Upload Time",
            cell: item => timeago(item.update_epoch * 1000) || "-",
            sortingField: "update_epoch"
          },
          {
            id: "action",
            header: "Action",
            cell: item => {
              if (item.file_index_status !== "success_index_delete")
                return (<Button iconName="delete-marker" onClick={() => deleteByKey(item.file_id)}>Delete</Button>)
              else
                return null
            }
          }
        ]}
        enableKeyboardNavigation
        items={userFiles}
        loadingText="Loading Files"
        stickyHeader
        stripedRows
        sortingDisabled
        empty={
          <Box
            margin={{ vertical: "xs" }}
            textAlign="center"
            color="inherit"
          >
            <SpaceBetween size="m">
              <b>No Files</b>
            </SpaceBetween>
          </Box>
        }
      />
      <Modal
        size="small"
        onDismiss={() => {
          if (!isLoading) {
            setIsModalVisible(false)
          }
        }}
        visible={isModalVisible}
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setIsModalVisible(false)} disabled={isLoading}>Cancel</Button>
              <Button variant="primary" onClick={(event) => upload_file(event)} disabled={isLoading}>Save</Button>
            </SpaceBetween>
          </Box>
        }
        header="Upload file"
      >
        <FileUpload
          accept=".pdf,.png,.jpg"
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
        />
      </Modal>
    </Container>
  );


}