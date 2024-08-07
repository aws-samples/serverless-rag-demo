import {
  Alert,
  Button,
  Container,
  FileUpload,
  FormField,
  Grid,
  SpaceBetween,
  Spinner, Textarea
} from "@cloudscape-design/components";
import { useEffect, useLayoutEffect, useState, useContext } from "react";
import { ChatScrollState } from "./chat-ui";
import { ChatMessage, ChatMessageType } from "./types";
import axios from "axios";
import config from "../../config.json";
import { AppContext } from "../../common/context";

var ws = null;
var agent_prompt_flow = []
var msgs = null
var b64_content = []
var user_content = []

export interface ChatUIInputPanelProps {
  inputPlaceholderText?: string;
  sendButtonText?: string;
  running?: boolean;
  messages?: ChatMessage[];
  selected_model_option?: string;
  selected_language?: string;
  check_vector_db?: boolean;
  is_hybrid_search?: boolean;
  clear_socket?: boolean;
  onSendMessage?: (message: string, type: string) => void;
  userinfo?: any;
  notify_parent?: (message: string, notify_type: string) => void;
}

export default function ChatUIInputPanel(props: ChatUIInputPanelProps) {
  const [inputText, setInputText] = useState("");
  const [value, setValue] = useState<File[]>([]);
  const socketUrl = config.websocketUrl;
  const appData = useContext(AppContext);
  const [isDisabled, setDisabled] = useState(false);

  useEffect(() => {
    const onWindowScroll = () => {
      if (ChatScrollState.skipNextScrollEvent) {
        ChatScrollState.skipNextScrollEvent = false;
        return;
      }

      const isScrollToTheEnd =
        Math.abs(
          window.innerHeight +
          window.scrollY -
          document.documentElement.scrollHeight
        ) <= 10;

      if (!isScrollToTheEnd) {
        ChatScrollState.userHasScrolled = true;
      } else {
        ChatScrollState.userHasScrolled = false;
      }
    };

    window.addEventListener("scroll", onWindowScroll);

    return () => {
      window.removeEventListener("scroll", onWindowScroll);
    };
  }, []);

  useEffect(() => {
    if (props.clear_socket) {
      ws=null;
      agent_prompt_flow=[]
      setDisabled(false)
      msgs = null
      b64_content = []
      user_content = []
    }
  }, [props.clear_socket]);


  useLayoutEffect(() => {
    if (ChatScrollState.skipNextHistoryUpdate) {
      ChatScrollState.skipNextHistoryUpdate = false;
      return;
    }

    if (!ChatScrollState.userHasScrolled && (props.messages ?? []).length > 0) {
      ChatScrollState.skipNextScrollEvent = true;
      window.scrollTo({
        top: document.documentElement.scrollHeight + 1000,
        behavior: "instant",
      });
    }
  }, [props.messages]);


  function load_base64(file_value) {
    if (file_value.length > 0) {
      for (var i = 0; i < file_value.length; i++) {
        // File type should be pdf or jpg or png
        if (file_value[i].type !== "image/webp" && file_value[i].type !== "image/jpeg" && file_value[i].type !== "image/png" && file_value[i].type !== "image/gif") {
          notify("File type should be jpg or png or webp", "error")
          return 
        }
        // File size should be less than 30 MB
        if (file_value[i].size > 5 * 1024 * 1024) {
          notify("File size should be less than 5 MB", "error")
          return
        }

        var reader = new FileReader();
        reader.onload = function (e) {
          b64_content.push(e.target.result)
        };
        reader.readAsDataURL(file_value[i]);
      }
    }
    setValue(file_value)
  }

  const notify = (message, notify_type) => {
    props.notify_parent?.(message, notify_type);
  }

  const onSendMessage = () => {
    ChatScrollState.userHasScrolled = false;
    props.onSendMessage?.(inputText, ChatMessageType.Human);
    setInputText("");

    //const access_token = props.userinfo.tokens.accessToken.toString();

    if (inputText.trim() !== '') {
      if ("WebSocket" in window) {
        setDisabled(true)
        if (msgs) {
          agent_prompt_flow.push({ 'role': 'assistant', 'content': [{ "type": "text", "text": msgs }] })
          msgs = null
        }
        // Images/docs are attached
        if (value.length > 0) {
          for (var i = 0; i < value.length; i++) {
            var unique_file_id = crypto.randomUUID()
            var file_data = value[i]
            var file_name = file_data['name'];
            var period = file_name.lastIndexOf('.');
            var fileExtension = file_name.substring(period + 1);
            axios.post(
              config.apiUrl + 'file_data', null,
              {params: { "file_extension": fileExtension, "file_name": unique_file_id }, 
              headers: { authorization: appData.userinfo.tokens.idToken.toString() } }
            ).then((result) => {
              var formData = new FormData();
              formData = build_form_data(result['data']['result'], formData)
              formData.append('file', file_data);
              var upload_url = result['data']['result']['url']
              axios.post(upload_url, formData).then(function (result) {
                console.log('Upload successful')
                notify("File uploaded successfully", "info")
                // user_content.push({"type": "image", "source": { "type": "base64", "media_type": "image/png", "data": e.target.result }})
                // Extract file extension from base64 content
                var media_type = 'image/' + fileExtension
                var partial_s3_key = unique_file_id + '.' + fileExtension
                user_content.push({ "type": "image", "source": { "type": "base64", "media_type": media_type, "file_extension": fileExtension, "partial_s3_key": partial_s3_key } })
                if (i >= value.length - 1) {
                  user_content.push({ "type": "text", "text": inputText })
                }
                // Add user content to the agent prompt flow
                agent_prompt_flow.push({ 'role': 'user', 'content': user_content })
                if (i >= value.length - 1) {
                  send_over_socket();
                }
              }).catch(function (err) {
                notify("File upload error" + String(err), "error")
              })
              
            }).catch(function (err) {
              notify("File upload error" + String(err), "error")
            })
          }
        } else {
          user_content.push({ "type": "text", "text": inputText })
          // Add user content to the agent prompt flow
          agent_prompt_flow.push({ 'role': 'user', 'content': user_content })
          send_over_socket();
        }

      } else {
        notify("WebSocket is not supported by your browser.", "error")
        agent_prompt_flow = []
      }
    }
  };

  function build_form_data(result, formdata) {
    if ('fields' in result) {
      for (var key in result['fields']) {
        formdata.append(key, result['fields'][key])
      }
    }
    return formdata
  }

  function send_over_socket() {
    if (ws == null || ws.readyState == 3 || ws.readyState == 2) {

      var idToken = appData.userinfo.tokens.idToken.toString()
      ws = new WebSocket(socketUrl + "?access_token=" + idToken);
      ws.onerror = function (event) {
        console.log(event);
        notify("Websocket error" + String(event), "error")
        setDisabled(false);
      };
    } else {
      var query_vector_db = 'no';
      var hybrid_enabled = 'no';
      if (props.check_vector_db) {
        query_vector_db = 'yes';
      }
      if (props.is_hybrid_search) {
        hybrid_enabled = 'yes';
      }

      // query_vectordb allowed values -> yes/no
      ws.send(JSON.stringify({
        query: JSON.stringify(agent_prompt_flow),
        behaviour: 'advanced-rag-agent',
        'query_vectordb': query_vector_db,
        'is_hybrid_search': hybrid_enabled,
        'model_id': props.selected_model_option,
        'language': props.selected_language,
      }));
      user_content = [];
      setValue([]);

    }

    ws.onopen = () => {
      var query_vector_db = 'no';
      if (props.check_vector_db) {
        query_vector_db = 'yes';
      }
      if (props.is_hybrid_search) {
        hybrid_enabled = 'yes';
      }
      // query_vectordb allowed values -> yes/no
      ws.send(JSON.stringify({
        query: JSON.stringify(agent_prompt_flow),
        behaviour: 'advanced-rag-agent',
        'query_vectordb': query_vector_db,
        'is_hybrid_search': hybrid_enabled,
        'model_id': props.selected_model_option,
        'language': props.selected_language
      }));
      user_content = [];
      setValue([]);
    };

    ws.onmessage = (event) => {
      if (event.data.includes('message')) {
        var evt_json = JSON.parse(event.data);
        if (evt_json['message'].includes('Endpoint')) {
          evt_json['message'] = 'Hang in there'
        }
        props.onSendMessage?.(evt_json['message'], ChatMessageType.AI);
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
            setTimeout(()=> {
              setDisabled(false);
            },3000)
            
          }
          props.onSendMessage?.(msgs, ChatMessageType.AI);
        } else {
          // Display errors
          props.onSendMessage?.(chat_output, ChatMessageType.AI);
          setDisabled(false);
        }
      }

    };

    ws.onclose = () => {
      console.log('WebSocket connection closed');
      agent_prompt_flow = [];
      setDisabled(false);
    };
    ws.onerror = function (event) {
      console.log(event);
      notify("Websocket error" + String(event), "error")
      setDisabled(false);
    };
  }

  function capitalizeFirstLetter(val) {
    return val.charAt(0).toUpperCase() + val.slice(1);
  }

  const OnTextareaKeyDown = (event) => {
    if (!props.running && event.detail.key === "Enter" && !event.detail.shiftKey) {
      event.preventDefault()
      onSendMessage();
    }
  }

  return (<Container disableContentPaddings disableHeaderPaddings variant="embed">
    <SpaceBetween size="s">
      <Textarea
        spellcheck={true}
        rows={2}
        autoFocus
        onKeyDown={(event) => OnTextareaKeyDown(event)}
        onChange={({ detail }) => setInputText(detail.value)}
        value={inputText}
        placeholder={props.inputPlaceholderText ?? "Send a message"}
      />
      <SpaceBetween size="s" direction="horizontal">
      <FileUpload
          accept=".png,.jpg,.webp,.gif"
          onChange={({ detail }) => {
            load_base64(detail.value)
          }
          }
          value={value}
          i18nStrings={{
            uploadButtonText: e =>
              e ? "Choose files" : "",
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
        <Button
          disabled={props.running || isDisabled || inputText.trim().length === 0}
          onClick={onSendMessage}
          iconAlign="right"
          iconName={!props.running ? "angle-right-double" : undefined}
          variant="primary" >
          {props.running ? (
            <>
              Loading&nbsp;&nbsp;
              <Spinner />
            </>
          ) : (
            <>{props.sendButtonText ?? "Send"}</>
          )}
        </Button>

        
      </SpaceBetween>
    </SpaceBetween>
  </Container>);
}