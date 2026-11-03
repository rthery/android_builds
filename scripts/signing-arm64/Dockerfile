# Linux arm64 runtime for target-files packaging: native JDK, x86 otatools through Rosetta (libc6:amd64).
FROM ubuntu@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
COPY ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources
RUN dpkg --add-architecture amd64 && apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends openjdk-21-jre-headless python3 openssl zip unzip xz-utils libc6:amd64 \
 && apt-get clean && rm -rf /var/lib/apt/lists/*
