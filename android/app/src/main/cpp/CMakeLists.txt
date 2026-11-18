cmake_minimum_required(VERSION 3.22.1)
project(audiotarget_uvc C)

# USB cameras through Android's USB host API, for phones whose camera service
# doesn't offer USB cameras to apps (Pixels among them). See uvc_jni.c.

set(TP ${CMAKE_CURRENT_SOURCE_DIR}/third_party)

# libusb, as its own shared library (LGPL-2.1).
add_library(usb1.0 SHARED
    ${TP}/libusb/libusb/core.c
    ${TP}/libusb/libusb/descriptor.c
    ${TP}/libusb/libusb/hotplug.c
    ${TP}/libusb/libusb/io.c
    ${TP}/libusb/libusb/sync.c
    ${TP}/libusb/libusb/strerror.c
    ${TP}/libusb/libusb/os/linux_usbfs.c
    ${TP}/libusb/libusb/os/events_posix.c
    ${TP}/libusb/libusb/os/threads_posix.c
    ${TP}/libusb/libusb/os/linux_netlink.c)
target_include_directories(usb1.0
    PRIVATE ${TP}/libusb ${TP}/libusb/libusb/os
    PUBLIC ${TP}/libusb/libusb)
target_compile_options(usb1.0 PRIVATE -fvisibility=hidden -pthread -Wno-unused-parameter)
target_link_libraries(usb1.0 log)

# libuvc (BSD), linked into the JNI library.
add_library(uvc STATIC
    ${TP}/libuvc/src/ctrl.c
    ${TP}/libuvc/src/ctrl-gen.c
    ${TP}/libuvc/src/device.c
    ${TP}/libuvc/src/diag.c
    ${TP}/libuvc/src/frame.c
    ${TP}/libuvc/src/init.c
    ${TP}/libuvc/src/stream.c
    ${TP}/libuvc/src/misc.c)
target_include_directories(uvc PUBLIC ${TP}/libuvc/include)
# Android's usbfs rejects large isochronous URBs (libuvc issues 299, 326):
# small transfers, more of them.
target_compile_definitions(uvc PRIVATE
    LIBUVC_PACKETS_PER_TRANSFER_MAX=8
    LIBUVC_NUM_TRANSFER_BUFS=64)
set_target_properties(uvc PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_link_libraries(uvc PUBLIC usb1.0)

add_library(audiotarget_uvc SHARED uvc_jni.c)
target_compile_options(audiotarget_uvc PRIVATE -Wall -Wextra -Wno-unused-parameter)
target_link_libraries(audiotarget_uvc uvc log)
# 16 KB pages (Android 15+ devices)
target_link_options(audiotarget_uvc PRIVATE "-Wl,-z,max-page-size=16384")
target_link_options(usb1.0 PRIVATE "-Wl,-z,max-page-size=16384")
