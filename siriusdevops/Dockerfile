FROM nginx:alpine
COPY siriusdevops/index.html /usr/share/nginx/html/index.html
COPY siriusdevops/services.html /usr/share/nginx/html/services.html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:80/ || exit 1
