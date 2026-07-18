FROM caddy:2-alpine

COPY livekit-server /usr/local/bin/livekit-server

EXPOSE 7880 7881 7882/udp

ENTRYPOINT ["/usr/local/bin/livekit-server"]
