#pragma once

typedef struct {
  char ssid[32];
  char password[64];
  char key[256];
} wifi_config_data_t;

void uart_json_init(void (*on_config_ready)(const wifi_config_data_t *config));