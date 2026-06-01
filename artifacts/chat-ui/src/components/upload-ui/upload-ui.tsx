import { useContext, useEffect, useState, useMemo } from "react";
import {
  FileUpload, Button, SpaceBetween, Container, Header,
  Modal, Box, Table, Toggle, StatusIndicator, Pagination
} from "@cloudscape-design/components";
import { LoadingBar } from "@cloudscape-design/chat-components";
import { AppContext } from "../../common/context";
import {
  listDocuments, getUploadPresignedUrl, uploadMetadata,
  deleteDocument, syncKnowledgeBase, DocumentInfo
} from "../../common/document-service";

export interface UploadDocProps {
  running?: boolean;
  notify_parent?: (message: string, notify_type: string) => void;
}

export function UploadUI(props: UploadDocProps) {
  const [value, setValue] = useState<File[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [userFiles, setUserFiles] = useState<DocumentInfo[]>([]);
  const [globalView, setGlobalView] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const PAGE_SIZE = 20;
  const appData = useContext(AppContext);

  const getUserEmail = (): string => {
    return appData.userinfo?.signInDetails?.loginId || appData.userinfo?.username || "";
  };

  const getIdToken = (): string => {
    return appData.userinfo?.tokens?.idToken?.toString() || "";
  };

  const notify = (message: string, notify_type: string) => {
    props.notify_parent?.(message, notify_type);
  };

  const refreshFileList = async () => {
    setIsLoading(true);
    try {
      const docs = await listDocuments(getUserEmail(), getIdToken(), globalView);
      setUserFiles(docs);
    } catch (err: any) {
      notify(`Failed to list documents: ${err.message}`, "error");
    }
    setIsLoading(false);
  };

  useEffect(() => {
    if (appData.userinfo) {
      refreshFileList();
    }
  }, [appData, globalView]);

  const uploadFile = async () => {
    if (value.length === 0) return;
    setIsLoading(true);
    setIsModalVisible(false);

    const email = getUserEmail();
    const idToken = getIdToken();

    try {
      for (const file of value) {
        // Get presigned URL for upload
        const presignedUrl = await getUploadPresignedUrl(
          email, file.name, file.type || "application/octet-stream", idToken
        );

        // Upload file via presigned URL
        const response = await fetch(presignedUrl, {
          method: "PUT",
          body: file,
          headers: { "Content-Type": file.type || "application/octet-stream" },
        });

        if (!response.ok) {
          throw new Error(`Upload failed: ${response.statusText}`);
        }

        // Upload metadata sidecar
        await uploadMetadata(email, file.name, idToken);
      }

      notify("Files uploaded successfully. Syncing knowledge base...", "info");
      setValue([]);

      // Trigger KB sync
      await syncKnowledgeBase(idToken);
      notify("Knowledge base sync started. Files will be searchable in a few minutes.", "info");

      refreshFileList();
    } catch (err: any) {
      notify(`Upload failed: ${err.message}`, "error");
      setIsLoading(false);
    }
  };

  const handleDelete = async (doc: DocumentInfo) => {
    if (!confirm(`Delete ${doc.fileName}?`)) return;

    setIsLoading(true);
    try {
      await deleteDocument(doc.key, getIdToken());
      notify("File deleted. Syncing knowledge base...", "info");
      await syncKnowledgeBase(getIdToken());
      refreshFileList();
    } catch (err: any) {
      notify(`Delete failed: ${err.message}`, "error");
      setIsLoading(false);
    }
  };

  const paginatedFiles = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return userFiles.slice(start, start + PAGE_SIZE);
  }, [userFiles, currentPage]);

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  return (
    <Container
      fitHeight
      variant="embed"
      header={
        <Header
          actions={
            <SpaceBetween direction="horizontal" size="s">
              <Toggle
                checked={globalView}
                onChange={({ detail }) => { setGlobalView(detail.checked); setCurrentPage(1); }}
              >
                Show all users
              </Toggle>
              <Button iconName="refresh" onClick={refreshFileList} disabled={isLoading}>
                Refresh
              </Button>
              <Button onClick={() => setIsModalVisible(true)} disabled={isLoading} variant="primary">
                Upload File
              </Button>
            </SpaceBetween>
          }
          variant="h2"
        >
          Documents
        </Header>
      }
    >
      {isLoading && <LoadingBar variant="gen-ai" />}
      <Table
        variant="full-page"
        columnDefinitions={[
          {
            id: "fileName",
            header: "File Name",
            cell: (item) => item.fileName,
            sortingField: "fileName",
            isRowHeader: true,
          },
          {
            id: "owner",
            header: "Owner",
            cell: (item) => item.isOwner ? (
              <StatusIndicator type="success">You</StatusIndicator>
            ) : item.userEmail,
          },
          {
            id: "size",
            header: "Size",
            cell: (item) => formatSize(item.size),
          },
          {
            id: "lastModified",
            header: "Last Modified",
            cell: (item) => item.lastModified.toLocaleDateString(),
          },
          {
            id: "action",
            header: "Action",
            cell: (item) =>
              item.isOwner ? (
                <Button iconName="delete-marker" onClick={() => handleDelete(item)} disabled={isLoading}>
                  Delete
                </Button>
              ) : null,
          },
        ]}
        items={paginatedFiles}
        loadingText="Loading documents..."
        wrapLines
        resizableColumns
        stickyHeader
        stripedRows
        sortingDisabled
        pagination={
          <Pagination
            currentPageIndex={currentPage}
            pagesCount={Math.ceil(userFiles.length / PAGE_SIZE)}
            onChange={({ detail }) => setCurrentPage(detail.currentPageIndex)}
          />
        }
        empty={
          <Box margin={{ vertical: "xs" }} textAlign="center" color="inherit">
            <SpaceBetween size="m">
              <b>No documents</b>
              <p>Upload documents to start using RAG search.</p>
            </SpaceBetween>
          </Box>
        }
      />

      <Modal
        size="small"
        onDismiss={() => !isLoading && setIsModalVisible(false)}
        visible={isModalVisible}
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setIsModalVisible(false)} disabled={isLoading}>
                Cancel
              </Button>
              <Button variant="primary" onClick={uploadFile} disabled={isLoading || value.length === 0}>
                Upload
              </Button>
            </SpaceBetween>
          </Box>
        }
        header="Upload document"
      >
        <FileUpload
          accept=".pdf,.txt,.md,.html,.doc,.docx,.csv"
          onChange={({ detail }) => setValue(detail.value)}
          value={value}
          i18nStrings={{
            uploadButtonText: (e) => (e ? "Choose files" : "Choose file"),
            dropzoneText: (e) => (e ? "Drop files to upload" : "Drop file to upload"),
            removeFileAriaLabel: (e) => `Remove file ${e + 1}`,
            limitShowFewer: "Show fewer files",
            limitShowMore: "Show more files",
            errorIconAriaLabel: "Error",
          }}
          showFileLastModified
          showFileSize
        />
      </Modal>
    </Container>
  );
}
