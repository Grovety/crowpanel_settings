#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "portmacro.h"

#include "cJSON.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_crc.h"
#include "esp_log.h"

#include "string.h"

#include "uart.h"

#define UART_NUM UART_NUM_0
#define BUF_SIZE 512

#if UART_NUM == UART_NUM_0
#define UART_RX_PIN GPIO_NUM_44
#define UART_TX_PIN GPIO_NUM_43
#elif UART_NUM == UART_NUM_1
#define UART_RX_PIN GPIO_NUM_19
#define UART_TX_PIN GPIO_NUM_20
#endif

static const char *TAG = "UART_JSON";

static QueueHandle_t queue = NULL;

static void (*config_callback)(const wifi_config_data_t *config) = NULL;

static void uart_send_str(const char *str) {
  uart_write_bytes(UART_NUM, str, strlen(str));
}

static bool validate_and_parse_json(const char *json_str,
                                    wifi_config_data_t *out) {
  cJSON *root = cJSON_Parse(json_str);
  if (!root)
    return false;

  const cJSON *ssid = cJSON_GetObjectItem(root, "SSID");
  const cJSON *pass = cJSON_GetObjectItem(root, "pass");
  const cJSON *key = cJSON_GetObjectItem(root, "key");
  const cJSON *crc = cJSON_GetObjectItem(root, "crc32");

  if (!cJSON_IsString(ssid) || !cJSON_IsString(pass) || !cJSON_IsString(key) ||
      !cJSON_IsString(crc)) {
    cJSON_Delete(root);
    return false;
  }

  char pure_json[256];
  snprintf(pure_json, sizeof(pure_json),
           "{\"SSID\":\"%s\",\"key\":\"%s\",\"pass\":\"%s\"}",
           ssid->valuestring, key->valuestring, pass->valuestring);

  ESP_LOGI(TAG, "Pure JSON: %s", pure_json);
  uint32_t calc_crc = esp_crc32_le(0, (uint8_t *)pure_json, strlen(pure_json));
  ESP_LOGI(TAG, "CRC32: %08lX", calc_crc);
  char calc_str[9];
  snprintf(calc_str, sizeof(calc_str), "%08lX", (unsigned long)calc_crc);

  if (strcasecmp(calc_str, crc->valuestring) != 0) {
    ESP_LOGE(TAG, "CRC mismatch: received=%s, expected=%s", crc->valuestring,
             calc_str);
    uart_send_str("CRC ERROR\n");
    cJSON_Delete(root);
    return false;
  }

  strncpy(out->ssid, ssid->valuestring, sizeof(out->ssid) - 1);
  strncpy(out->password, pass->valuestring, sizeof(out->password) - 1);
  strncpy(out->key, key->valuestring, sizeof(out->key) - 1);

  cJSON_Delete(root);
  return true;
}

static void uart_json_task(void *arg) {
  uint8_t buf[BUF_SIZE];
  size_t buffered_size = 0;
  wifi_config_data_t config;

  while (1) {
    uart_event_t event;
    xQueueReceive(queue, (void *)&event, (TickType_t)portMAX_DELAY);
    switch (event.type) {
    // Event of UART receiving data
    /*We'd better handler data event fast, there would be much more
    data events than other types of events. If we take too much time
    on data event, the queue might be full.*/
    case UART_DATA: {
      uart_read_bytes(UART_NUM, &buf[buffered_size], event.size, portMAX_DELAY);
      buffered_size += event.size;
      if (!event.timeout_flag)
        break;
      ESP_LOGI(TAG, "[UART DATA]: %u, %d", buffered_size,
               event.timeout_flag ? 1 : 0);
      ESP_LOG_BUFFER_HEXDUMP(TAG, buf, buffered_size, ESP_LOG_INFO);
      buf[buffered_size] = '\0';
      if (validate_and_parse_json((char *)buf, &config)) {
        uart_send_str("Success\n");
        printf("SSID: %s\n", config.ssid);
        printf("Password: %s\n", config.password);
        printf("Key: %s\n", config.key);
        if (config_callback) {
          config_callback(&config);
        }
      } else {
        uart_send_str("Error parsing JSON\n");
      }
      buffered_size = 0;
      break;
    }
    case UART_BUFFER_FULL: {
      uart_send_str("UART overflow\n");
      buf[0] = '\0';
      buffered_size = 0;
      break;
    }
    default:
      break;
    }
  }
}

void uart_json_init(void (*on_config_ready)(const wifi_config_data_t *config)) {
  uart_config_t cfg = {
      .baud_rate = 115200,
      .data_bits = UART_DATA_8_BITS,
      .parity = UART_PARITY_DISABLE,
      .stop_bits = UART_STOP_BITS_1,
      .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
  };

  ESP_ERROR_CHECK(
      uart_driver_install(UART_NUM, BUF_SIZE * 2, BUF_SIZE * 2, 20, &queue, 0));
  ESP_ERROR_CHECK(uart_param_config(UART_NUM, &cfg));
  ESP_ERROR_CHECK(uart_set_pin(UART_NUM, UART_TX_PIN, UART_RX_PIN,
                               UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));

  config_callback = on_config_ready;

  BaseType_t ret =
      xTaskCreate(uart_json_task, "uart_json_task", 6144, NULL, 10, NULL);
  if (ret != pdPASS) {
    ESP_LOGE(TAG, "Unable to create UART task");
  }
}