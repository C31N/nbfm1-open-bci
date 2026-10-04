# SPDX-License-Identifier: CERN-OHL-S-2.0
cmake_minimum_required(VERSION 3.13)

include(pico_sdk_import.cmake)

project(eeg128_tdm C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(
    eeg128_tdm
    main.cpp
)

target_link_libraries(
    eeg128_tdm
    pico_stdlib
    hardware_dma
    hardware_gpio
    hardware_irq
    hardware_spi
    hardware_sync
    hardware_timer
)

pico_enable_stdio_usb(eeg128_tdm 1)
pico_enable_stdio_uart(eeg128_tdm 0)
pico_add_extra_outputs(eeg128_tdm)
