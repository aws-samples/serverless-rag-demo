import { useState, useEffect } from "react";
import {
  Container,
  ContentLayout,
  Header,
  Button,
  Grid,
  SpaceBetween,
} from "@cloudscape-design/components";
import { withAuthenticator } from '@aws-amplify/ui-react';
import { AppPage } from "../common/types";
import { AuthHelper } from "../common/helpers/auth-help";
import Textarea from "@cloudscape-design/components/textarea";
import * as React from "react"
import style from "../styles/agent-ui.module.scss";
import { AppContext } from "../common/context";
import config from "../config.json";

var default_customer_review = `Sample Customer review. 
I got our devices working, and I figured out how the devices work together in conjunction with the (necessary) Alexa app on your phone and your home wifi. We just have the basic set up right now; no home management or security devices. We have 3 echo dot's (2nd gen) and are using them successfully in our 1300 sq ft home in 3 different rooms.
If you have more than one device you can change the names of the devices on the amazon site. Note that each device actually has a unique assigned code and you can see that on each of the device boxes when they arrive. To keep track of multiple devices, I would suggest that you hang on to the boxes and put a note on each box as to the unique name you have assigned to it and where in your house it's located.

Setup:
I thought the set up was not an intuitive process, and you are doing it without any good instructions...so it kind of sucks. Hopefully the below tips will help you!

You have to start with a good modem, good router, good internet access (we have cox). Then you have to have a have a smartphone with a data package that is hooked to your home wifi. Phone has to have the Amazon Alexa app downloaded from your app store. Bonus if you have Amazon Prime because you will have access to a lot of free content there (music etc) but don’t think the prime account is required.

The dot devices will use the Alexa app and the wifi connection on your phone to hook to your home wifi. You cannot, it seems, make a direct connect from the dot to the wifi/router. At one point during the process the Alexa app turns off the phone's wifi for a time which kind of threw me off as I thought something was going wrong, but just keep moving forward and follow the Alexa app directions and it all works out in the end. If you have more than one dot, each dot has to be set up individually.

A note that during the process I did discover that my modem was having problems and kept dropping internet signal, especially after I added all these devices. All of a sudden, especially at night, the Alexa app on the phone couldn’t find an internet connection even though my phone wifi indicated that it was connected, and then the dot devices weren’t operating correctly. It seems that if the Alexa app loses it’s connection to wifi (via your phone) the dot devices may not work right. Got a new modem and only one problem since. I should add that I also have a Galaxy S7 phone which has apparently had problems with the Alexa application.

What you can do…lots!
All 3 of our dots are able to use any of the skills enabled on the Alexa app. I have timers, shopping lists, to do lists, google calendar, alarms, Pandora, local NPR stream, can search for local movie times, get news flashes, weather anywhere in the world, play some games ...and there are lots more ‘skills’ that can be added. It's actually really cool, and I find the ability to give a voice command to search for information a time saver, even if (at this point) the info you can search for is limited...it's not like using Google, but does alot.

Amazon sends new info, updates etc via daily email. So far they have been very prompt replying to support questions. They offer little games you can play for Amazon gift cards and the like which adds some extra fun into it.

The speaker on the Echo dot is good for music or sleep sounds in a smallish area. We have the Dot in the living room set to play thru our big home theater speaker system, so that dot, and only that dot, has a 'paired Bluetooth link' to the receiver. Once the initial pair is set up for the dot device, you just need to make sure the receiver is set to Bluetooth and ask Alexa to link to the receiver. Once linked, all responses from that dot device will be through the speakers. So once linked, just ask the dot to open Pandora, or play an artist or album. If you want it unlinked from the speakers, just give it a verbal command. We actually choose to leave that living room dot device linked to the speakers most of the time and it works great for us. We have rarely ever have more than one of our dots pick up a command. It only happened once, and we just had music playing in 2 rooms, which was easily corrected.

A few minor quirks we have encountered:
1. if we are playing sleep sounds (rain, ocean, thunderstorms etc) the device sometimes has trouble hearing commands. Same happens if I have a fan running in the bedroom. It sometimes has trouble hearing commands.
2. It is unable to pick up on Google Calendar notifications and automatically give me a verbal reminder. It can give you your calendar for the day and it can add to the calendar
3. Sometimes it has a little trouble understanding my shopping list item or task list item
4. Once an item is added to calendar, shopping list or to do list it has to be removed manually. ie; go to Alexa app and remove it from the shopping or task list, or go to calendar and remove from the calendar using phone or computer.`

var default_sentiment_placeholder = `{
  "sentiment": "neutral"
}`

var ws = null
var msgs = null
function SentimentPage(props: AppPage) {
  const [value, setValue] = React.useState(default_customer_review);
  const [out, setOut] = React.useState("");
  const appData = React.useContext(AppContext);
  const socketUrl = config.websocketUrl;
  useEffect(() => {
    const init = async () => {
      let userdata = await AuthHelper.getUserDetails();
      props.setAppData({
        userinfo: userdata
      })
    }
    init();
  },[])

  const onSubmitReview = () => {
    if ("WebSocket" in window) {
      if (value.length > 0) {
        setOut("")
        msgs=null
        send_over_socket()
      }
    }
  }

  const send_over_socket = () => {
    if (ws == null || ws.readyState == 3 || ws.readyState == 2) {
      let idToken = appData.userinfo.tokens.idToken.toString();
      ws = new WebSocket(socketUrl + "?access_token=" + idToken);
      ws.onerror = function (event) {
        console.log(event);
      };
    } else {
      
      ws.send(JSON.stringify({
        query: JSON.stringify([{"role": "user", "content": [{"type": "text", "text": value}]}]),
        behaviour: 'sentiment',
        'query_vectordb': "no",
        'model_id': "anthropic.claude-3-haiku-20240307-v1:0"
      }));
    }

    ws.onopen = () => {
      // query_vectordb allowed values -> yes/no
      ws.send(JSON.stringify({
        query: JSON.stringify([{"role": "user", "content": [{"type": "text", "text": value}]}]),
        behaviour: 'sentiment',
        'query_vectordb': 'no',
        'model_id': "anthropic.claude-3-haiku-20240307-v1:0"
      }));
      
    };

    ws.onmessage = (event) => {
      if (event.data.includes('message')) {
        var evt_json = JSON.parse(event.data);
        setOut(out + evt_json['message'])
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
          setOut(msgs)
          msgs=null
        }
        
      } else {
        // Display errors
        setOut(chat_output)
      }
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
          Sentiment Analysis
        </Header>
      }
    >
      <Container
        fitHeight
      >
        <Grid gridDefinition={[
      { colspan: { xxs: 5, xs: 5, s: 5, m: 6, l: 5, xl: 5 } },
      { colspan: { xxs: 2, xs: 2, s: 2, m: 1, l: 2, xl: 2 } },
      { colspan: { xxs: 5, xs: 5, s: 5, m: 5, l: 5, xl: 5 } }]}
    > 
    <div>
    <Textarea
      onChange={({ detail }) => setValue(detail.value)}
      value={value}
      placeholder={default_customer_review}
      rows={15}
    />
    <SpaceBetween size="l"></SpaceBetween>
    <Button
          iconAlign="right"
          onClick={onSubmitReview}
          variant="primary" >Submit
        </Button>
    </div>

    <div className={style.vertical_line}></div>
    
    <Textarea
      // onChange={({ detail }) => setOut(detail.value)}
      readOnly={true}
      value={out}
      placeholder={default_sentiment_placeholder}
      rows={15}
    />
    
      </Grid>
        

      </Container>
    </ContentLayout>
  );
}

export default withAuthenticator(SentimentPage)