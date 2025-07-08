import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import serial
import serial.tools.list_ports
import json
import zlib
import os
import threading

BAUD_RATE = 115200
SETTINGS_FILE = "settings.json"
stop_reader = False  
ser = None 

def start_read_thread():
    def read_serial():
        global stop_reader
        while not stop_reader:
            try:
                if ser and ser.is_open and ser.in_waiting:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        log_text.after(0, append_log, line)

                        if line == "CRC ERROR":
                            send_to_panel(False)

            except Exception as e:
                print("Serial Error:", e)
                pass

    t = threading.Thread(target=read_serial, daemon=True)
    t.start()

def calculate_crc32(data: dict) -> str:
    json_data = json.dumps(data, separators=(',', ':'), sort_keys=True).encode()
    print(json_data);
    crc = zlib.crc32(json_data)
    print(format(crc, '08X'));
    return format(crc, '08X')

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_settings(data: dict):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        messagebox.showerror("Error", f"Couldn't save settings:\n{e}")

def send_to_panel(f):
    global ser, stop_reader

    ssid = ssid_entry.get()
    password = pass_entry.get()
    key = key_entry.get()
    com_port = combo.get()

    if not all([ssid, password, key]):
        messagebox.showerror("Error", "Please fill in all fields.")
        return

    if not com_port:
        messagebox.showerror("Error", "Please select the COM port.")
        return

    payload = {
        "SSID": ssid,
        "pass": password,
        "key": key
    }
    payload["crc32"] = calculate_crc32(payload)

    try:
        json_str = json.dumps(payload)

        if ser is None or not ser.is_open:
            ser = serial.Serial(com_port, BAUD_RATE, timeout=1)
            stop_reader = False
            start_read_thread()

        ser.write((json_str + '\n').encode('utf-8'))
        if f:
            messagebox.showinfo("Complete", "The settings were sent successfully.")
            save_settings({
                "SSID": ssid,
                "pass": password,
                "key": key,
                "COM_PORT": com_port
            })

    except serial.SerialException as e:
        if f:
            messagebox.showerror("Error", f"Couldn't open the port {com_port}:\n{e}")
    except Exception as e:
        if f:
            messagebox.showerror("Error", f"An error has occurred:\n{e}")

def get_com_ports():
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

def append_log(text):
    log_text.insert(tk.END, text + "\n")
    log_text.see(tk.END)

# --- GUI ---

root = tk.Tk()
root.title("Settings")
root.geometry("700x450")
root.minsize(400, 300)

default_font = ("Arial", 14)

root.grid_columnconfigure(1, weight=1)
root.grid_rowconfigure(6, weight=1)


tk.Label(root, text="SSID:", font=default_font).grid(row=0, column=0, sticky="e", padx=5, pady=5)
ssid_entry = tk.Entry(root, width=30, font=default_font)
ssid_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

tk.Label(root, text="Password:", font=default_font).grid(row=1, column=0, sticky="e", padx=5, pady=5)
pass_entry = tk.Entry(root, width=30, font=default_font)
pass_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

tk.Label(root, text="Key:", font=default_font).grid(row=2, column=0, sticky="e", padx=5, pady=5)
key_entry = tk.Entry(root, width=30, font=default_font)
key_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

tk.Label(root, text="COM-port:", font=default_font).grid(row=3, column=0, sticky="e", padx=5, pady=5)
ports = get_com_ports()  
combo = ttk.Combobox(root, values=ports, state="readonly", width=27, font=default_font)
combo.grid(row=3, column=1, sticky="ew", padx=5, pady=5)

def refresh_ports():
    new_ports = get_com_ports()
    combo['values'] = new_ports
    if new_ports:
        combo.current(0)

def disconnect():
    global ser, stop_reader
    stop_reader = True
    if ser and ser.is_open:
        ser.close()
        append_log("Disconnected from board.")
    else:
        append_log("Already disconnected.")


send_button = tk.Button(root, text="Send", command=lambda: send_to_panel(True), font=default_font)
send_button.grid(row=4, column=0, pady=15, padx=5, sticky="e")

disconnect_button = tk.Button(root, text="Disconnect", command=disconnect, font=default_font)
disconnect_button.grid(row=4, column=1, pady=15, padx=5, sticky="w")

refresh_button = tk.Button(root, text="⟳", command=refresh_ports, font=default_font)
refresh_button.grid(row=3, column=2, padx=5, pady=5)

tk.Label(root, text="Messages from the board:", font=default_font).grid(row=5, column=0, columnspan=2)
log_text = scrolledtext.ScrolledText(root, width=60, height=10, font=default_font, state="disabled")
log_text.grid(row=6, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)

def append_log(text):
    log_text.configure(state="normal")
    log_text.insert("end", text + "\n")
    log_text.configure(state="disabled")
    log_text.see("end") 

settings = load_settings()
if settings.get("SSID"): ssid_entry.insert(0, settings["SSID"])
if settings.get("pass"): pass_entry.insert(0, settings["pass"])
if settings.get("key"): key_entry.insert(0, settings["key"])

saved_port = settings.get("COM_PORT")
if saved_port in ports:
    combo.set(saved_port)
elif ports:
    combo.current(0)

def on_close():
    global stop_reader, ser
    stop_reader = True
    if ser and ser.is_open:
        ser.close()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)
root.mainloop()
