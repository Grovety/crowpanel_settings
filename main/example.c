#include "uart.h"
#include <string.h>

wifi_config_data_t wifi_data;

void on_uart_settings_received(const wifi_config_data_t *data) {
    memcpy(&wifi_data, data, sizeof(wifi_config_data_t));
}

void app_main() {
    uart_json_init(on_uart_settings_received);
}