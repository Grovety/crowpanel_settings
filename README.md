# The application for saving settings on ESP32-S3

## Project Overview

This project is an application that allows you to enter settings and save them on ESP32-S3.

It includes two main components:

### 1. Python script
- Parameters:
  - SSID
  - Password
  - Key
  - COM port
- Generates a crc32
- Save parametrs
- Show messages from board

### 2. ESP-idf script
- Divides the data into a structure

## How to use Python script

1. [Download Python](https://www.python.org/downloads/) (if not installed)  
2. Install required Python packages:

    ```bash
    python -m pip install pyserial
    ```

3. Launch `app.py` from the `python` folder

    ```bash
    python python/app.py
    ```

4. Fill in the fields: **SSID**, **Password**, **KEY**  
5. Select the COM port of your device (to refresh the list, use the **⟳** button)  
6. Press the **Send** button (all settings will be saved in `settings.json`)
7. If you see something like this in the "Messages from board" field, it means the board received all settings correctly:

    ```bash
    SSID: 1111
    Password: 1111
    Key: 1111
    ```
8. To update the firmware on the board, use the **Disconnect** button before updating.

### Example usage

Below is an example screenshot showing the application with filled fields and a successful response from the board:

![App screenshot showing filled fields and response](images/app_screenshot.png)

*Example of filled fields and successful response from the board.*

## How to use C script

1. Download and install [ESP-IDF extension for VS Code](https://marketplace.visualstudio.com/items?itemName=espressif.esp-idf-extension)
2. Copy `uart.c` and `uart.h` files into your project folder
3. Add the following line to your `CMakeLists.txt` in the project folder to include `uart.c`:

      ```cmake
      idf_component_register(SRCS "uart.c" INCLUDE_DIRS ".")
      ```

4. To save settings via UART, call:

      ```c
      uart_json_init(on_uart_settings_received);
      ```

    You need to provide the callback function `on_uart_settings_received`, for example:

      ```c
      wifi_config_data_t wifi_data;

      void on_uart_settings_received(const wifi_config_data_t *data) {
          memcpy(&wifi_data, data, sizeof(wifi_config_data_t));
      }
      ```

5. After that, the settings will be saved into the `wifi_data` structure:
   - SSID → `wifi_data.ssid`
   - Password → `wifi_data.password`
   - Key → `wifi_data.key`

9. **Make sure the ESP-IDF Monitor is closed** before using the Python script. The COM port must be free.

### C code example

Below is an example of project code in VS Code :

  ```c
  #include "uart.h"
  #include <string.h>

  wifi_config_data_t wifi_data;
  
  void on_uart_settings_received(const wifi_config_data_t *data) {
      memcpy(&wifi_data, data, sizeof(wifi_config_data_t));
  }

  void app_main() {
      uart_json_init(on_uart_settings_received);
  }
  ```

  CMakeLists.txt example

  ```cmake
  idf_component_register(SRCS "example.c" "uart.c"
                        INCLUDE_DIRS ".")
  ```
  