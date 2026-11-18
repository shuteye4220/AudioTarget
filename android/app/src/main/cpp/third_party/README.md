Vendored sources, unmodified except where noted:

- libusb v1.0.27 (LGPL-2.1, see libusb/COPYING): https://github.com/libusb/libusb
  Built as its own shared library (libusb1.0.so), as the LGPL allows.
- libuvc at commit 7955bb1 (BSD, see libuvc/LICENSE.txt): https://github.com/libuvc/libuvc
  libuvc_config.h is written by hand (no JPEG: the app decodes MJPEG with OpenCV).
