# Build image plus the arm64 libraries the native aarch64 JDK needs (LineageOS 22.2 builds).
# amd64 comes from a dated Ubuntu snapshot; snapshot.ubuntu.com has no ports archive, so arm64
# uses ports.ubuntu.com with exact versions and the build fails once one is superseded.
FROM registry.gitlab.e.foundation:5000/e/os/docker-lineage-cicd@sha256:786a3e13b33249109e74741abef42bcc2fdf00ca0b619145b82eabe7f3ad4d84
ARG SNAPSHOT=20261027T000000Z
RUN set -eux; \
    rm -f /etc/apt/sources.list /etc/apt/sources.list.d/*; \
    printf '%s\n' \
      'Types: deb' 'Architectures: amd64' "URIs: http://snapshot.ubuntu.com/ubuntu/$SNAPSHOT/" \
      'Suites: noble noble-updates noble-security' 'Components: main universe' \
      'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg' '' \
      'Types: deb' 'Architectures: arm64' 'URIs: http://ports.ubuntu.com/ubuntu-ports/' \
      'Suites: noble noble-updates noble-security' 'Components: main universe' \
      'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg' > /etc/apt/sources.list.d/snapshot.sources; \
    dpkg --add-architecture arm64; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      libc6:arm64=2.39-0ubuntu8.9 \
      zlib1g:arm64=1:1.3.dfsg-3.1ubuntu2.3 zlib1g:amd64=1:1.3.dfsg-3.1ubuntu2.3 \
      libbrotli1:arm64=1.1.0-2ubuntu0.1 libbrotli1:amd64=1.1.0-2ubuntu0.1 \
      libfontconfig1:arm64=2.15.0-1.1ubuntu2 libfreetype6:arm64=2.13.2+dfsg-1ubuntu0.2 \
      libexpat1:arm64=2.6.1-2ubuntu0.6 libpng16-16t64:arm64=1.6.43-5ubuntu0.7 libbz2-1.0:arm64=1.0.8-5.1ubuntu0.1; \
    rm -rf /var/lib/apt/lists/*; \
    dpkg-query -W -f='${Package}:${Architecture} ${Version}\n' | sort > /etc/rom-runner-packages.txt
