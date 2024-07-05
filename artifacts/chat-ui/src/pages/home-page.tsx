import {
    Container,
    ContentLayout,
    Header
  } from "@cloudscape-design/components";
  
  export default function HomePage() {
    return (
      <ContentLayout
        defaultPadding
        headerVariant="high-contrast"
        header={
          <Header
            variant="h1"
            description="App description will come here"
          >
            Home
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
  