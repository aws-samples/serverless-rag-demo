import {
  Container,
  ContentLayout,
  Header,
  Button,
} from "@cloudscape-design/components";

export default function NotFound() {
  return (
    <ContentLayout
      defaultPadding
      headerVariant="high-contrast"
      header={
        <Header
          variant="h1"
          description="The page you are looking for does not exist."
        >
          Page Not Found
        </Header>
      }
    >
      <Container
      fitHeight
        header={
          <Header variant="h2">#404</Header>
        }
      >
        <Button variant="primary" href="/">Home</Button>
      </Container>
    </ContentLayout>
  );
}
