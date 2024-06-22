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
import Table from "@cloudscape-design/components/table";
import Box from "@cloudscape-design/components/box";
import TextFilter from "@cloudscape-design/components/text-filter";
import Header from "@cloudscape-design/components/header";
import Pagination from "@cloudscape-design/components/pagination";
import CollectionPreferences from "@cloudscape-design/components/collection-preferences";
import Icon from "@cloudscape-design/components/icon";

export function UploadUI() {

  const [value, setValue] = React.useState<File[]>([]);
  const [showFlashbar, setShowFlashbar] = React.useState(false)
  const [selectedItems, setSelectedItems] = React.useState([{}]);
  const [file_upload_table_items, setFileUploadTableItems] = React.useState([{
    file_index_status: "",
    file_id: "",
    idx_err_msg: "",
    index_timestamp: "",
    sort_key: "",
    s3_source: "",
    update_epoch: "",
    upload_timestamp: ""
  }]);
  const [file_upload_table_cols, setFileUploadTableCols] = React.useState([
    {
      id: "s3_source",
      header: "S3 Source",
      cell: item => item.s3_source,
      sortingField: "s3_source"
    },
    {
      id: "file_index_status",
      header: "Index Status",
      cell: item => item.file_index_status,
      sortingField: "file_index_status"
    },
    {
      id: "upload_timestamp",
      header: "Upload Timestamp",
      cell: item => item.upload_timestamp,
      sortingField: "upload_timestamp"
    },
    {
      id: "idx_err_msg",
      header: "Index erorr message",
      cell: item => item.idx_err_msg,
      sortingField: "idx_err_msg"
    },
    {
      id: "delete_icon",
      header: "Delete File",
      cell: item => <Icon name="delete-marker" />,
    }
  ]);
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

  function load_history() {
    axios.get(config.apiUrl + 'get-indexed-files-by-user',
      {
        headers: { authorization: StorageHelper.getAuthToken() }
      }).then(function (result) {
        console.log(result['data']['result'])
        setFileUploadTableItems(result['data']['result'])
      }).catch(function (err) {
        console.log(err)
      })
  }

  React.useEffect(() => {
    load_history()
  }, [])

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
      file_name_no_ext = file_name_no_ext.replace(/\s/g, '-')
      file_name_no_ext = file_name_no_ext.replace(/[^0-9a-z-]/gi, '')
      var fileExtension = file_name.substring(period + 1);
      axios.get(config.apiUrl + 'get-presigned-url', {
        params: { "file_extension": fileExtension, "file_name": file_name_no_ext },
        headers: {
          authorization: StorageHelper.getAuthToken(),
        }
      }) // Handle the response from backend here
        .then(function (result) {
          var formData = new FormData();
          formData = build_form_data(result['data']['result'], formData)
          formData.append('file', file_data);
          var upload_url = result['data']['result']['url']
          axios.post(upload_url, formData)
            .then(function (result) {
              setItems([generate_flashbar_message('File uploaded successfully', false)])
              // TODO:  Open a websocket listener here to listen on indexing status
            }).catch(function (err) {
              console.log(err)
              setItems([generate_flashbar_message('Error uploading file', false)])
            })
            // Catch errors if any
            .catch((err) => {
              console.log(err)
              setItems([generate_flashbar_message('Error generating presigned url', false)])
            });

        }).catch((err) => {
          console.log(err)
        })
    }
  }

  return (
    <FormField
      label="Form field label"
      description="Description"
    >
      {showFlashbar ? <Flashbar items={items} /> : null}
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
      <br /><br />
      <SpaceBetween direction="horizontal" size="xs">
        <Button variant="primary" onClick={(event) => upload_file(event)}>Index Document</Button>
        <Button onClick={(event) => delete_index()} >Delete All</Button>

        <Table
          renderAriaLive={({
            firstIndex,
            lastIndex,
            totalItemsCount
          }) =>
            `Displaying items ${firstIndex} to ${lastIndex} of ${totalItemsCount}`
          }
          onSelectionChange={({ detail }) =>
            setSelectedItems(detail.selectedItems)
          }
          selectedItems={selectedItems}
          ariaLabels={{
            selectionGroupLabel: "Items selection",
            allItemsSelectionLabel: ({ selectedItems }) =>
              `${selectedItems.length} ${selectedItems.length === 1 ? "item" : "items"
              } selected`,
            itemSelectionLabel: ({ selectedItems }, item) =>
              item.name
          }}
          columnDefinitions={file_upload_table_cols}
          columnDisplay={[
            { id: "s3_source", visible: true },
            { id: "file_index_status", visible: true },
            { id: "upload_timestamp", visible: true },
            { id: "idx_err_msg", visible: true },
            { id: "delete_icon", visible: true }
          ]}
          enableKeyboardNavigation
          items={file_upload_table_items}
          loadingText="Loading resources"
          selectionType="multi"
          trackBy="name"
          empty={
            <Box
              margin={{ vertical: "xs" }}
              textAlign="center"
              color="inherit"
            >
              <SpaceBetween size="m">
                <b>No resources</b>
                <Button>Create resource</Button>
              </SpaceBetween>
            </Box>
          }
          filter={
            <TextFilter
              filteringPlaceholder="Find resources"
              filteringText=""
            />
          }
          header={
            <Header
              counter={
                selectedItems.length
                  ? "(" + selectedItems.length + "/50)"
                  : "(50)"
              }
            >
              File Upload History
            </Header>
          }
          // pagination={
          //   <Pagination currentPageIndex={1} pagesCount={2} />
          // }
          preferences={
            <CollectionPreferences
              title="Preferences"
              confirmLabel="Confirm"
              cancelLabel="Cancel"
              preferences={{
                pageSize: 50,
                contentDisplay: [
                  { id: "variable", visible: true },
                  { id: "value", visible: true },
                  { id: "type", visible: true },
                  { id: "description", visible: true }
                ]
              }}
              pageSizePreference={{
                title: "Page size",
                options: [
                  { value: 50, label: "50 resources" },
                  { value: 100, label: "100 resources" },
                  { value: 200, label: "200 resources" },
                  { value: 300, label: "300 resources" },
                  { value: 400, label: "400 resources" }
                ]
              }}
              wrapLinesPreference={{}}
              stripedRowsPreference={{}}
              contentDensityPreference={{}}
              contentDisplayPreference={{
                options: [
                  {
                    id: "variable",
                    label: "Variable name",
                    alwaysVisible: true
                  },
                  { id: "value", label: "Text value" },
                  { id: "type", label: "Type" },
                  { id: "description", label: "Description" }
                ]
              }}
              stickyColumnsPreference={{
                firstColumns: {
                  title: "S3 Source",
                  description:
                    "Keep the first column(s) visible while horizontally scrolling the table content.",
                  options: [
                    { label: "None", value: 0 },
                    { label: "First column", value: 1 },
                    { label: "First two columns", value: 2 }
                  ]
                },
                lastColumns: {
                  title: "Stick last column",
                  description:
                    "Keep the last column visible while horizontally scrolling the table content.",
                  options: [
                    { label: "None", value: 0 },
                    { label: "Last column", value: 1 }
                  ]
                }
              }}
            />
          }
        />

      </SpaceBetween>

    </FormField>
  );
}