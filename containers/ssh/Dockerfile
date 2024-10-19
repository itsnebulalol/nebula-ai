FROM alpine:3.20

RUN set -x && \
    apk upgrade --no-cache --available && \
    apk add --no-cache curl ca-certificates bash

COPY _fs/. /
RUN chmod +x /usr/sbin/harden.sh && \
    /usr/sbin/harden.sh ; :