# Chat UI Cloudscape App

[https://cloudscape.design/](https://cloudscape.design/)

Cloudscape is an open source design system for the cloud. Cloudscape offers user interface guidelines, front-end components, design resources, and development tools for building intuitive, engaging, and inclusive user experiences at scale.


![sample](../assets/chat-ui-vite.png "Screenshot")


## Vite.js

[https://vitejs.dev/](https://vitejs.dev/)

Vite.js is a modern, fast front-end build tool that significantly improves the developer experience when building web applications. 

## Development
1. Clone this repository to your local machine
```bash
git clone https://github.com/aws-samples/cloudscape-examples
cd cloudscape-examples/chat-ui-vite
```
2. Install the project dependencies by running:
```bash
npm install
```
3. To start the development server, run:
```bash
npm run dev
```

This command will start a local development server at ``http://localhost:3000`` (or a different port if 3000 is in use). The server will hot-reload if you make edits to any of the source files.

## Building the App
To build the application for production, run:
```bash
npm run build
```
This command will generate a dist folder containing the production build of your app. Vite optimizes your project for the best performance during this process.

## Running the App Locally
After building the app, you can serve it locally using:
```bash
npm run preview
```
This command serves the production build from the dist folder, allowing you to preview the app before deployment.