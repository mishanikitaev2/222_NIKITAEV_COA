FROM node:16-alpine AS builder
WORKDIR /app

# Копируем proto-файл из локальной папки
COPY content.proto .
COPY gateway.proto .
COPY package*.json .

RUN npm install



COPY apiGateway.js .

EXPOSE 3000
CMD ["node", "apiGateway.js"]