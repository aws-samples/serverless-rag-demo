FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
FROM nginx:stable-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 3001
CMD ["nginx", "-g", "daemon off;"]

# COPY public/ /react-docker/public
# COPY src/ /react-docker/src
# COPY package.json /react-docker/
# COPY postcss.config.js /react-docker/
# COPY prettier.config.js /react-docker/
# COPY tsconfig.json /react-docker/
# COPY vite.config.ts /react-docker/
# COPY .eslintrc.cjs /react-docker/
# COPY tsconfig.node.json /react-docker/
# RUN npm install
# CMD ["npm", "run", "dev"]