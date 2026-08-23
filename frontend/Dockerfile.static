FROM --platform=$BUILDPLATFORM node:22-alpine AS build

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend ./
COPY README.md /app/README.md
COPY deREADME.md /app/deREADME.md
COPY docs /app/docs
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine

ENV VITE_API_BASE_URL=same-origin
ENV BPSTRACKER_DEFAULT_LANGUAGE=de

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html

EXPOSE 8080

# Avoid depending on wget/curl in minimal nginx images. The compose file maps the host
# frontend port to this unprivileged container port.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD test -s /usr/share/nginx/html/index.html && test -s /tmp/bpstracker-config/config.js && [ "$(cat /proc/1/comm 2>/dev/null)" = nginx ]

CMD ["/bin/sh", "-c", "mkdir -p /tmp/bpstracker-config && cat > /tmp/bpstracker-config/config.js <<EOF_CONF\nwindow.__BPSTRACKER_CONFIG__ = { API_BASE_URL: \"${VITE_API_BASE_URL:-same-origin}\", DEFAULT_LANGUAGE: \"${BPSTRACKER_DEFAULT_LANGUAGE:-${BPSTRACKER_LANGUAGE:-de}}\" };\nEOF_CONF\nexec nginx -g 'daemon off;'"]
