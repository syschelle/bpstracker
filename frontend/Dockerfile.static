FROM nginxinc/nginx-unprivileged:1.27-alpine

ENV VITE_API_BASE_URL=same-origin

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -qO- http://127.0.0.1:8080/health >/dev/null || exit 1

CMD ["/bin/sh", "-c", "mkdir -p /tmp/bpstracker-config && cat > /tmp/bpstracker-config/config.js <<EOF_CONF\nwindow.__BPSTRACKER_CONFIG__ = { API_BASE_URL: \"${VITE_API_BASE_URL:-same-origin}\" };\nEOF_CONF\nexec nginx -g 'daemon off;'"]
