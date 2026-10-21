cmake_minimum_required(VERSION 3.16)
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../../vendor/esp32-iq-tx/firmware")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(atum_modem_tx)
