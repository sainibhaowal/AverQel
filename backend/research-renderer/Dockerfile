FROM mcr.microsoft.com/playwright:v1.51.0-jammy
WORKDIR /srv/renderer
COPY package.json ./
RUN npm install --omit=dev --ignore-scripts
COPY server.mjs ./server.mjs
USER pwuser
EXPOSE 3010
CMD ["node", "server.mjs"]
