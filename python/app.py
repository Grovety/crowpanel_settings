import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext,Frame, Canvas, Scrollbar,filedialog
import serial
import serial.tools.list_ports
import json
import zlib
import os
import threading

BAUD_RATE = 115200
stop_reader = False  
ser = None
DEFAULT_FONT =("Arial",12)

pat="settings.txt"

def load_settings_file(filename: str) -> list[dict]:
    settings_data = []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(";")
                if len(parts) < 4:
                    raise ValueError("Invalid line format, expected 4 fields.")
                name, size, default, field_type = parts
                settings_data.append({
                    "name": name,
                    "size": int(size),
                    "default": default,
                    "type": field_type
                })
    except FileNotFoundError:
        messagebox.showerror("Error", f"File {filename} not found!")
    except Exception as e:
        messagebox.showerror("Error", f"While reading {filename}:\n{e}")
    return settings_data

settings_fields = {}  

def create_dynamic_gui(parent_frame, settings_data):
    global pat
    
    if pat:
        filename = os.path.basename(pat)
        root.title(f"Settings - {filename}")
    else:
        root.title("Settings")
        
    for widget in parent_frame.winfo_children():
        widget.destroy()
    def rebuild_field(setting, row):
        for child in parent_frame.grid_slaves(row=row, column=1):
            child.destroy()

        if setting["type"] == "bool":
            var = tk.BooleanVar(value=(str(setting["default"]).lower() == "true"))
            cb = tk.Checkbutton(parent_frame, variable=var)
            cb.grid(row=row, column=1, sticky="w", padx=5, pady=5)
            settings_fields[setting["name"]] = var
        else:
            entry = tk.Entry(parent_frame, width=30, font=("Arial", 12))
            entry.insert(0, setting["default"])
            entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)
            settings_fields[setting["name"]] = entry

    for i, setting in enumerate(settings_data):
        tk.Label(parent_frame, text=f"{setting['name']}:", font=("Arial", 12)).grid(
            row=i, column=0, sticky="e", padx=5, pady=5
        )

        rebuild_field(setting, i)

        type_combo = ttk.Combobox(
            parent_frame, values=["str", "int", "bool"], state="readonly", font=("Arial", 10)
        )
        type_combo.set(setting["type"])
        type_combo.grid(row=i, column=2, padx=5, pady=5)

        def on_type_change(event, s=setting, row=i):
            s["type"] = event.widget.get()
            rebuild_field(s, row)

        type_combo.bind("<<ComboboxSelected>>", on_type_change)
        setting["type_widget"] = type_combo

    row = len(settings_data)
    tk.Label(parent_frame, text="COM-port:", font=("Arial", 12)).grid(row=row, column=0, sticky="e", padx=5, pady=5)

    ports = get_com_ports()
    global combo
    combo = ttk.Combobox(parent_frame, values=ports, state="readonly", font=("Arial", 12))
    combo.grid(row=row, column=1, sticky="ew", padx=5, pady=5)
    if ports:
        combo.current(0)

    global status_label
    status_label = tk.Label(parent_frame, text="●", font=("Arial", 40), fg="red")
    status_label.grid(row=row, column=2, padx=5, pady=5)
        

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
    data_for_crc = data.copy()
    data_for_crc.pop("crc32", None)
    
    json_str = json.dumps(data_for_crc, separators=(',', ':'), ensure_ascii=False)
    json_str = json_str.replace(" ", "")

    print("FINAL JSON FOR CRC:", repr(json_str))
    crc = zlib.crc32(json_str.encode('utf-8'))
    return format(crc & 0xFFFFFFFF, '08x').upper()

def save_settings(filename: str) -> list[dict]:
    try:
        lines = []
        for setting in settings_data:
            name = setting["name"]
            size = setting["size"]
            field_type = setting["type_widget"].get()

            if field_type == "bool":
                value = "true" if settings_fields[name].get() else "false"
            else:
                value = settings_fields[name].get()

            lines.append(f"{name};{size};{value};{field_type}\n")

        with open(filename, "w", encoding="utf-8") as f:
            f.writelines(lines)

    except Exception as e:
        messagebox.showerror("Error", f"Couldn't save settings:\n{e}")

def send_to_panel(f):
    global ser, stop_reader,pat
    save_settings(pat)

    payload = {}
    for name, entry in settings_fields.items():
        value = entry.get()
        if not value:
            messagebox.showerror("Error", f"Field {name} is empty!")
            return

        field_type = None
        for setting in settings_data: 
            if setting["name"] == name:
                field_type = setting.get("type", "str")
                break

        if field_type == "int":
            try:
                value = int(value)  # Entry → число
            except ValueError:
                messagebox.showerror("Error", f"Field {name} must be an integer!")
                return

        payload[name] = value

    com_port = combo.get()
    if not com_port:
        messagebox.showerror("Error", "Please select the COM port.")
        return

    payload["crc32"] = calculate_crc32(payload) 

    try:
        json_str = json.dumps(payload)
        print("Sending JSON:", json_str) 
        if ser is None or not ser.is_open:
            ser = serial.Serial(com_port, BAUD_RATE, timeout=1)
            stop_reader = False
            start_read_thread()

        ser.write((json_str + '\n').encode('utf-8'))
        if f:
            messagebox.showinfo("Complete", "The settings were sent successfully.")

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
root.geometry("1150x450")
root.minsize(1150, 450)

canvas = Canvas(root)
scrollbar = Scrollbar(root, orient="vertical", command=canvas.yview)
scrollable_frame = Frame(canvas)

scrollable_frame.bind(
    "<Configure>",
    lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
)
canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
canvas.configure(yscrollcommand=scrollbar.set)

canvas.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

settings_data = load_settings_file(pat)

create_dynamic_gui(scrollable_frame, settings_data)

combo_label = tk.Label(scrollable_frame, text="COM-port:", font=("Arial", 12))
combo_label.grid(row=len(settings_data), column=0, sticky="e", padx=5, pady=5)

def open_settings_file():
    global pat
    file_path = filedialog.askopenfilename(
        title="Open settings file",
        filetypes=(("TXT file", "*.txt"), ("All file", "*.*"))
    )

    if not file_path:
        return

    try:
        settings_data=load_settings_file(file_path)
        pat=file_path
        create_dynamic_gui(scrollable_frame, settings_data)
        messagebox.showinfo("Success", f"File {file_path} loaded")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load file: {e}")

def save_settings_as():
    global pat
    file_path = filedialog.asksaveasfilename(
        title="Save settings as",
        defaultextension=".txt",
        filetypes=(("TXT files", "*.txt"), ("All files", "*.*"))
    )
    if not file_path:
        return  
    try:
        save_settings(file_path)
        pat=file_path
        messagebox.showinfo("Success", f"Settings saved to:\n{file_path}")
    except Exception as e:
        messagebox.showerror("Error", f"Couldn't save settings:\n{e}")

menu_bar = tk.Menu(root)
root.config(menu=menu_bar)

file_menu = tk.Menu(menu_bar, tearoff=0)
menu_bar.add_cascade(label="File", menu=file_menu)

def add_field():
    add_win = tk.Toplevel(root)
    add_win.title("Add Field")

    tk.Label(add_win, text="Field name").grid(row=0, column=0)
    tk.Label(add_win, text="Field length").grid(row=1, column=0)
    tk.Label(add_win, text="Default value").grid(row=2, column=0)
    tk.Label(add_win, text="Data type").grid(row=3, column=0)

    name_entry = tk.Entry(add_win)
    name_entry.grid(row=0, column=1)
    size_entry = tk.Entry(add_win)
    size_entry.grid(row=1, column=1)
    default_entry = tk.Entry(add_win)
    default_entry.grid(row=2, column=1)
    type_combo = ttk.Combobox(add_win, values=["str", "int", "bool"], state="readonly")
    type_combo.grid(row=3, column=1)
    type_combo.current(0)

    def on_add():
        name = name_entry.get()
        size = size_entry.get()
        default = default_entry.get()
        ftype = type_combo.get()
        if not name or not size or not default:
            messagebox.showerror("Error", "All fields required!")
            return

        settings_data=load_settings_file(pat)
        settings_data.append({
            "name": name,
            "size": int(size),
            "default": default,
            "type": ftype
        })

        with open(pat, "a", encoding="utf-8") as f:
            f.write(f"{name};{size};{default};{ftype}\n")

        # Обновляем GUI
        create_dynamic_gui(scrollable_frame, settings_data)
        add_win.destroy()

    tk.Button(add_win, text="Add", command=on_add).grid(row=4, column=0, columnspan=2)

def remove_field():
    global pat
    remove_win = tk.Toplevel(root)
    remove_win.title("Remove Field")

    tk.Label(remove_win, text="Field name to remove").grid(row=0, column=0, padx=5, pady=5)
    name_entry = tk.Entry(remove_win)
    name_entry.grid(row=0, column=1, padx=5, pady=5)

    def on_remove():
        name = name_entry.get()
        if not name:
            messagebox.showerror("Error", "Please enter a field name!")
            return

        if not messagebox.askyesno("Confirm", f"Are you sure you want to remove field '{name}'?"):
            return

        file_path = pat
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = [line for line in lines if not line.startswith(f"{name};")]

            if len(new_lines) == len(lines):
                messagebox.showerror("Error", f"No field named '{name}' found in file!")
                return

            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            messagebox.showinfo("Success", f"Field '{name}' removed from file.")

            global settings_data
            settings_data = load_settings_file(file_path)
            create_dynamic_gui(scrollable_frame, settings_data)
            remove_win.destroy()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to remove field:\n{e}")

    tk.Button(remove_win, text="Remove", command=on_remove).grid(row=1, column=0, columnspan=2, pady=5)

file_menu.add_command(label="Open", command=open_settings_file)
file_menu.add_command(label="Save as", command=save_settings_as)

field_menu = tk.Menu(menu_bar, tearoff=0)
menu_bar.add_cascade(label="Field", menu=field_menu)
field_menu.add_command(label="Add Field", command=add_field)
field_menu.add_command(label="Remove Field", command=remove_field)
def update_connection_status():
    global ser
    try:
        if not combo or not combo.winfo_exists():
            status_label.config(fg="red")
            return

        port = combo.get()
        if not port:
            status_label.config(fg="red")
            return

        if ser and ser.is_open:
            status_label.config(fg="green")
        else:
            try:
                with serial.Serial(port, BAUD_RATE, timeout=1) as test_ser:
                    if test_ser.is_open:
                        status_label.config(fg="green")
                    else:
                        status_label.config(fg="red")
            except serial.SerialException:
                status_label.config(fg="red")
    except Exception:
        status_label.config(fg="red")

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


button_frame = Frame(root)
button_frame.pack(side="bottom", fill="x", padx=5, pady=5)

send_button = tk.Button(button_frame, text="Send", command=lambda: send_to_panel(True), font=("Arial", 12))
send_button.pack(side="left", padx=5)

disconnect_button = tk.Button(button_frame, text="Disconnect", command=disconnect, font=("Arial", 12))
disconnect_button.pack(side="left", padx=5)

refresh_button = tk.Button(button_frame, text="⟳", command=refresh_ports, font=("Arial", 12))
refresh_button.pack(side="left", padx=5)

log_label = ttk.Label(root, text="Messages from the board:", font=DEFAULT_FONT)
log_label.pack(pady=5)

log_text = scrolledtext.ScrolledText(root, width=60, height=10, font=DEFAULT_FONT)
log_text.pack(fill="both", expand=True, padx=5, pady=5)

def on_close():
    global stop_reader, ser
    stop_reader = True
    if ser and ser.is_open:
        ser.close()
    root.destroy()
    
def periodic_check():
    update_connection_status()
    root.after(1000, periodic_check)  # каждые 1000 мс

periodic_check()

root.protocol("WM_DELETE_WINDOW", on_close)
root.mainloop()
