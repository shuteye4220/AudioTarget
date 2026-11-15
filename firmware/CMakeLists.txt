cmake_minimum_required(VERSION 3.20.0)

# Bluetooth link is on unless -DAT_BLE=OFF.
option(AT_BLE "Include the Bluetooth LE link" ON)
if(AT_BLE)
	list(APPEND EXTRA_CONF_FILE ${CMAKE_CURRENT_LIST_DIR}/ble.conf)
endif()

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(audiotarget)

target_sources(app PRIVATE
	src/main.c
	src/audio.c
	src/buttons.c
	src/cues.c
	src/fusion.c
	src/imu.c
	src/link.c
	src/mount.c
	src/proto.c
	src/store.c
	src/tonemap.c
)
