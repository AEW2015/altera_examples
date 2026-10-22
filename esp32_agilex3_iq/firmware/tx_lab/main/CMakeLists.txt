set(amp "${CMAKE_CURRENT_LIST_DIR}/../../original_iq_tx_probe/main/main.c")
set(native "${CMAKE_CURRENT_LIST_DIR}/../../wifi64_tx/main/main.c")
set(phase "${CMAKE_CURRENT_LIST_DIR}/../../esp32_tx_probe/main/main.c")
idf_component_register(SRCS "main.c" "${amp}" "${native}" "${phase}" "../../esp32_tx_probe/main/probe_protocol.c"
 INCLUDE_DIRS "." "../../original_iq_tx_probe/main" "../../esp32_tx_probe/main"
 REQUIRES esp_event esp_phy esp_wifi nvs_flash esp_timer esp_driver_uart esp_hw_support)
set_source_files_properties("${amp}" PROPERTIES COMPILE_DEFINITIONS "app_main=txlab_amp_main")
set_source_files_properties("${native}" PROPERTIES COMPILE_DEFINITIONS "app_main=txlab_native_main")
set_source_files_properties("${phase}" PROPERTIES COMPILE_DEFINITIONS "app_main=txlab_phase_main")
target_compile_definitions(${COMPONENT_LIB} PRIVATE ATUM_TX_LAB_UNIFIED=1)
target_compile_options(${COMPONENT_LIB} PRIVATE -fstack-usage)
