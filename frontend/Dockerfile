# frontend/Dockerfile
FROM node:16

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install

COPY . .

RUN npm run build

CMD ["npx", "serve", "-s", "build", "-l", "3000"]