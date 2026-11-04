# OPTIONAL NEW CODESPACE IMAGE, NOT automatically applied to the running Codespace.
# Installs the exact FULL official Unity 6000.3.26f1 Linux Editor at image build
# time, not into the writable layer after Codespace creation.
# Verify the Docker image in a separate Codespace and back up dirty assets
# before considering any rebuild of musical-carnival-jjxp9r6vw45wfjgvg.
FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG UNITY_VERSION=6000.3.26f1
ARG UNITY_CHANGESET=de8167e7440c
ARG UNITY_EDITOR_URL=https://download.unity3d.com/download_unity/de8167e7440c/LinuxEditorInstaller/Unity-6000.3.26f1.tar.xz

# Minimal VS Code + GUI + Git LFS tooling, NOT an incomplete Unity Editor.
# No Conda, PHP, Go, Ruby, Node version managers, or random Android SDKs.
# Android Build Support, SDK/NDK/JDK can be added later as an image-build
# module, after separately validating the Android build requirements.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates curl xz-utils git git-lfs openssh-client \
      python3 python3-pip \
      xvfb x11vnc websockify novnc openbox xterm mesa-utils \
      libgtk-3-0 libglu1-mesa libx11-6 libxi6 libxcursor1 \
      libxrandr2 libxcomposite1 libxdamage1 libxfixes3 libxrender1 \
      libglib2.0-0 libnss3 libgbm1 libpulse0 libasound2t64 \
      libfontconfig1 libfreetype6; \
    git lfs install --system; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    if ! id codespace >/dev/null 2>&1; then \
      useradd --create-home --shell /bin/bash codespace; \
    fi; \
    mkdir -p "/home/codespace/Unity/Hub/Editor/${UNITY_VERSION}"; \
    curl --fail --location --show-error --silent --retry 4 \
      "${UNITY_EDITOR_URL}" -o /tmp/aaris-unity-editor.tar.xz; \
    tar -tJf /tmp/aaris-unity-editor.tar.xz >/dev/null; \
    tar -xJf /tmp/aaris-unity-editor.tar.xz \
      -C "/home/codespace/Unity/Hub/Editor/${UNITY_VERSION}"; \
    rm -f /tmp/aaris-unity-editor.tar.xz; \
    test -x "/home/codespace/Unity/Hub/Editor/${UNITY_VERSION}/Editor/Unity"; \
    chown -R codespace:codespace /home/codespace/Unity

USER codespace
ENV HOME=/home/codespace
WORKDIR /workspaces/Unity-Game-Aris
# Never COPY game Assets/ or Library/ into the Docker image: project and
# imported Library belong on the persistent /workspaces volume.
# Never bake a Unity account, license secret or GitHub token into the image.
