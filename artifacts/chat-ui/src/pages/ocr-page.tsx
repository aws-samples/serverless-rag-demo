import {
  Container,
  ContentLayout,
  Header,
  Button,
} from "@cloudscape-design/components";
import { useState, useEffect } from "react";
import { withAuthenticator, useAuthenticator } from '@aws-amplify/ui-react';
import { AppPage } from "../common/types";
import { AuthHelper } from "../common/helpers/auth-help";


function OcrPage(props: AppPage) {
  useEffect(() => {
    const init = async () => {
      let userdata = await AuthHelper.getUserDetails();
      props.setAppData({
        userinfo: userdata
      })
    }
    init();
  },[])
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

      </Container>
    </ContentLayout>
  );
}


export default withAuthenticator(OcrPage)