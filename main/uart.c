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

#include "nvs_flash.h"
#include "nvs.h"

#define UART_NUM UART_NUM_0
#define BUF_SIZE 2048  

#if UART_NUM == UART_NUM_0
#define UART_RX_PIN GPIO_NUM_44
#define UART_TX_PIN GPIO_NUM_43
#elif UART_NUM == UART_NUM_1
#define UART_RX_PIN GPIO_NUM_19
#define UART_TX_PIN GPIO_NUM_20
#endif

#define namespace "app-setings"

static const char *TAG = "UART_JSON";
static QueueHandle_t uart_queue = NULL;

typedef struct {
    char name[32];    
    char value[128]; 
} config_param_t;

static void (*config_callback)(const config_param_t *params, int count) = NULL;

static void uart_send_str(const char *str) {
    uart_write_bytes(UART_NUM, str, strlen(str));
}

char* remove_all_spaces(const char *str) {
    char *result = malloc(strlen(str) + 1);
    char *ptr = result;
    while (*str) {
        if (*str != ' ') *ptr++ = *str;
        str++;
    }
    *ptr = '\0';
    return result;
}

static esp_err_t save_param_to_nvs(const char *name, const char *value) {
    nvs_handle_t nvs_handle;
    esp_err_t err = nvs_open(namespace, NVS_READWRITE, &nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS open failed");
        return err;
    }
    err = nvs_set_str(nvs_handle, name, value);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS set failed for %s", name);
        nvs_close(nvs_handle);
        return err;
    }
    err = nvs_commit(nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS commit failed");
    }
    nvs_close(nvs_handle);
    return err;
}

static bool parse_dynamic_json(const char *json_str, config_param_t *params, int *count) {
    char *json_no_spaces = remove_all_spaces(json_str);
    
    cJSON *root = cJSON_Parse(json_no_spaces);
    if (!root) {
        ESP_LOGE(TAG, "Failed to parse JSON");
        return false;
    }

    cJSON *crc = cJSON_GetObjectItem(root, "crc32");
    if (crc && cJSON_IsString(crc)) {
                cJSON *copy = cJSON_CreateObject();
        cJSON *item = NULL;
        cJSON_ArrayForEach(item, root) {
            if (strcmp(item->string, "crc32") != 0) {
                cJSON_AddItemToObject(copy, item->string, cJSON_Duplicate(item, 1));
            }
        }

        char *json_without_crc = cJSON_PrintUnformatted(copy);
        ESP_LOG_BUFFER_HEXDUMP(TAG, (uint8_t *)json_without_crc, strlen(json_without_crc), ESP_LOG_INFO);
        uint32_t calc_crc = esp_crc32_le(0, (uint8_t *)json_without_crc, strlen(json_without_crc));
        char calc_str[9];
        snprintf(calc_str, sizeof(calc_str), "%08lX", calc_crc);
        
        if (strcasecmp(calc_str, crc->valuestring) != 0) {
            ESP_LOGE(TAG, "CRC mismatch: calc=%s, recv=%s", calc_str, crc->valuestring);
            cJSON_Delete(root);
            cJSON_Delete(copy);
            free(json_without_crc);
            uart_send_str("CRC ERROR\n");
            return false;
        }
        cJSON_Delete(copy);
        free(json_without_crc);
    }

    *count = 0;
    root = cJSON_Parse(json_str);
    cJSON *item = NULL;
    cJSON_ArrayForEach(item, root) {
        if (strcmp(item->string, "crc32") == 0) continue;  
        const char *key = item->string;
        const char *type_str = "unknown";

        if (cJSON_IsString(item)) {
            type_str = "str";
            strlcpy(params[*count].name, key, sizeof(params[*count].name));
            strlcpy(params[*count].value, item->valuestring, sizeof(params[*count].value));
            save_param_to_nvs(key, item->valuestring);  
        } else if (cJSON_IsNumber(item)) {
            type_str = "int";
            int val = item->valueint;
            strlcpy(params[*count].name, key, sizeof(params[*count].name));
            snprintf(params[*count].value, sizeof(params[*count].value), "%d", val);

            nvs_handle_t nvs_handle;
            if (nvs_open(namespace, NVS_READWRITE, &nvs_handle) == ESP_OK) {
                nvs_set_i32(nvs_handle, key, val);
                nvs_commit(nvs_handle);
                nvs_close(nvs_handle);
            }
        } else if (cJSON_IsBool(item)) {
            type_str = "bool";
            int val = cJSON_IsTrue(item) ? 1 : 0;
            strlcpy(params[*count].name, key, sizeof(params[*count].name));
            snprintf(params[*count].value, sizeof(params[*count].value), "%d", val);

            nvs_handle_t nvs_handle;
            if (nvs_open(namespace, NVS_READWRITE, &nvs_handle) == ESP_OK) {
                nvs_set_u8(nvs_handle, key, val);
                nvs_commit(nvs_handle);
                nvs_close(nvs_handle);
            }
        }

        ESP_LOGI(TAG, "Param: %s = %s (%s)", params[*count].name, params[*count].value, type_str);
        (*count)++;
    }

    cJSON_Delete(root);
    return (*count > 0);
}

static void uart_json_task(void *arg) {
    uint8_t buf[BUF_SIZE];
    size_t buffered_size = 0;
    config_param_t params[20]; 
    int param_count = 0;

    while (1) {
        uart_event_t event;
        if (xQueueReceive(uart_queue, &event, portMAX_DELAY)) {
            switch (event.type) {
                case UART_DATA:
                    uart_read_bytes(UART_NUM, &buf[buffered_size], event.size, portMAX_DELAY);
                    buffered_size += event.size;
                    
                    if (event.timeout_flag) {
                        buf[buffered_size] = '\0';
                        ESP_LOGI(TAG, "Received JSON: %s", buf);
                        
                        if (parse_dynamic_json((char *)buf, params, &param_count)) {
                            uart_send_str("OK\n");
                            if (config_callback) {
                                config_callback(params, param_count);
                            }
                        } else {
                            uart_send_str("ERROR\n");
                        }
                        buffered_size = 0;
                    }
                    break;
                    
                case UART_BUFFER_FULL:
                    ESP_LOGE(TAG, "UART buffer full");
                    buffered_size = 0;
                    uart_send_str("BUFFER FULL\n");
                    break;
                    
                default:
                    break;
            }
        }
    }
}

void uart_json_init(void (*on_config_ready)(const config_param_t *params, int count)) {

    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    uart_config_t cfg = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
    };

    ESP_ERROR_CHECK(uart_driver_install(UART_NUM, BUF_SIZE * 2, BUF_SIZE * 2, 20, &uart_queue, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_NUM, &cfg));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM, UART_TX_PIN, UART_RX_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));

    xTaskCreate(uart_json_task, "uart_json_task", 8192, NULL, 10, NULL);
}