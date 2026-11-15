#!/bin/bash -e
# Runs on the build host. The release workflow has copied the repo's pi/ and
# image/ folders into files/ (see .github/workflows/release.yml).
install -d "${ROOTFS_DIR}/opt/audiotarget"
rm -rf "${ROOTFS_DIR}/opt/audiotarget/src"
cp -a files/src "${ROOTFS_DIR}/opt/audiotarget/src"

on_chroot <<CHROOT
AUDIOTARGET_IN_CHROOT=1 bash /opt/audiotarget/src/image/install.sh
CHROOT
