import hashlib
import json
import os
import serial
import serial.tools.list_ports
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image
import pystray
from pystray import MenuItem as item

# Set modern theme default
ctk.set_appearance_mode("System")  # Options: "System", "Dark", "Light"
ctk.set_default_color_theme("blue")


def get_asset_path(filename):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, filename)


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        if self.tooltip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 20

        self.tooltip_window = ctk.CTkToplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

        label = ctk.CTkLabel(
            self.tooltip_window,
            text=self.text,
            justify="left",
            corner_radius=6,
            fg_color=("gray80", "gray25"),
            text_color=("gray10", "gray90"),
            padx=8,
            pady=4,
        )
        label.pack()

    def hide_tooltip(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


class CollapsibleSection(ctk.CTkFrame):
    def __init__(self, parent, title="", **kwargs):
        super().__init__(parent, **kwargs)
        self.title = title
        self.is_expanded = True

        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=2, pady=2)

        self.toggle_btn = ctk.CTkButton(
            self.header_frame,
            text=f"▼  {self.title}",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
            fg_color="transparent",
            hover_color=("gray80", "gray30"),
            text_color=("black", "white"),
            command=self.toggle,
        )
        self.toggle_btn.pack(side="left", fill="x", expand=True, padx=4)

        # Container for extra buttons; only packed when populated
        self.header_extras = ctk.CTkFrame(self.header_frame, fg_color="transparent")

        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="x", padx=5, pady=(0, 5))

    def toggle(self):
        if self.is_expanded:
            self.content_frame.pack_forget()
            self.toggle_btn.configure(text=f"▶  {self.title}")
            self.is_expanded = False
        else:
            self.content_frame.pack(fill="x", padx=5, pady=(0, 5))
            self.toggle_btn.configure(text=f"▼  {self.title}")
            self.is_expanded = True


class ESPConfigApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ESP-Config Tool")
        self.serial_port = None
        self.is_connected = False
        self.handshake_received = False
        self.current_password = ""
        self.show_config_messages = False
        self.hide_ack_messages = False
        self.tabs = {}
        self.rendered_items = {}
        self.tray_icon = None

        # Sequence & Message Tracking
        self.tx_message_number = 0
        self.last_rx_message_num = 0
        self.received_msg_numbers = set()
        self.highest_contiguous_rx = 0

        self.setup_ui()
        self.setup_window_and_tray_icon()
        self.refresh_ports()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_window_and_tray_icon(self):
        icon_filename = "app_icon.png"
        icon_path = get_asset_path(icon_filename)

        if os.path.exists(icon_path):
            try:
                self.tk_icon = tk.PhotoImage(file=icon_path)
                self.root.iconphoto(True, self.tk_icon)
            except Exception as e:
                self.log_to_prog(f"Warning: Could not set window icon: {e}")

            try:
                pil_img = Image.open(icon_path)
                menu = pystray.Menu(
                    item("Show App", self.show_window), item("Quit", self.on_closing)
                )
                self.tray_icon = pystray.Icon(
                    "esp_config", pil_img, "ESP-Config Tool", menu
                )
                self.tray_icon.run_detached()
            except Exception as e:
                self.log_to_prog(f"Warning: Could not initialize system tray: {e}")
        else:
            self.log_to_prog(
                f"Warning: Icon file '{icon_filename}' not found at path: {icon_path}"
            )

    def show_window(self, icon=None, item=None):
        self.root.after(0, self.root.deiconify)
        self.root.after(0, self.root.lift)

    def change_theme_mode(self, new_mode):
        ctk.set_appearance_mode(new_mode)

    def setup_ui(self):
        # 1. Connection Controls & Top-Right Search Bar
        control_frame = ctk.CTkFrame(self.root)
        control_frame.pack(pady=5, padx=5, fill="x")

        ctk.CTkLabel(control_frame, text="COM Port:").pack(side="left", padx=(8, 2))
        self.port_cb = ctk.CTkComboBox(control_frame, width=120, values=[])
        self.port_cb.pack(side="left", padx=5)

        ctk.CTkButton(
            control_frame,
            text="Refresh",
            width=80,
            text_color="white",
            command=self.refresh_ports,
        ).pack(side="left", padx=2)

        self.connect_btn = ctk.CTkButton(
            control_frame,
            text="Connect",
            width=90,
            fg_color="#10B981",
            hover_color="#059669",
            text_color="white",
            command=self.toggle_connection,
        )
        self.connect_btn.pack(side="left", padx=2)

        ctk.CTkLabel(
            control_frame,
            text="Tip: Reconnect to re-populate list if missing items",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color=("gray40", "gray60"),
        ).pack(side="left", padx=10)

        # Search Bar
        search_frame = ctk.CTkFrame(control_frame, fg_color="transparent")
        search_frame.pack(side="right", padx=5)

        ctk.CTkLabel(
            search_frame, text="Search:", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(0, 4))
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.apply_filter())
        self.search_entry = ctk.CTkEntry(
            search_frame, textvariable=self.search_var, width=140
        )
        self.search_entry.pack(side="left")

        # 2. Password Frame
        self.pass_frame = ctk.CTkFrame(self.root)
        self.pass_frame.pack(pady=5, padx=5, fill="x")

        ctk.CTkLabel(self.pass_frame, text="Password:").pack(side="left", padx=(8, 2))
        self.pass_entry = ctk.CTkEntry(self.pass_frame, show="*", width=140)
        self.pass_entry.pack(side="left", padx=5)
        ctk.CTkButton(
            self.pass_frame,
            text="Set Password",
            width=100,
            text_color="white",
            command=self.set_password,
        ).pack(side="left", padx=5)

        self.pass_status = ctk.CTkLabel(
            self.pass_frame, text="Status: Not Set", text_color=("gray40", "gray60")
        )
        self.pass_status.pack(side="left", padx=10)

        self.pass_hint = ctk.CTkLabel(
            self.pass_frame,
            text="Hint: (Waiting for device...)",
            text_color=("#1D4ED8", "#60A5FA"),
        )
        self.pass_hint.pack(side="left", padx=5)

        # 3. Dynamic Category Tabs
        self.notebook = ctk.CTkTabview(self.root)
        self.notebook.pack(pady=5, padx=5, fill="both", expand=True)

        # 4. Serial Monitor
        monitor_frame = ctk.CTkFrame(self.root)
        monitor_frame.pack(pady=5, padx=5, fill="both", expand=True)

        monitor_header = ctk.CTkFrame(monitor_frame, fg_color="transparent")
        monitor_header.pack(fill="x", anchor="w", padx=5, pady=2)

        ctk.CTkLabel(
            monitor_header,
            text="Serial Monitor (Device Output):",
            font=ctk.CTkFont(weight="bold"),
        ).pack(side="left")

        self.show_config_var = ctk.BooleanVar(value=False)
        self.show_config_chk = ctk.CTkCheckBox(
            monitor_header,
            text="Show [config] Messages",
            variable=self.show_config_var,
            command=self.toggle_config_visibility,
        )
        self.show_config_chk.pack(side="left", padx=(15, 5))

        self.hide_ack_var = ctk.BooleanVar(value=False)
        self.hide_ack_chk = ctk.CTkCheckBox(
            monitor_header,
            text="Hide 'ack' Messages",
            variable=self.hide_ack_var,
            command=self.toggle_config_visibility,
            state="disabled",
        )
        self.hide_ack_chk.pack(side="left", padx=5)

        self.monitor = ctk.CTkTextbox(monitor_frame, height=120, wrap="word")
        self.monitor.configure(state="disabled")
        self.monitor.pack(fill="both", expand=True, padx=5, pady=5)

        # 5. Program Monitor
        prog_frame = ctk.CTkFrame(self.root)
        prog_frame.pack(pady=5, padx=5, fill="both")

        ctk.CTkLabel(
            prog_frame,
            text="Program Debug (Software Output):",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=5, pady=2)

        self.prog_monitor = ctk.CTkTextbox(prog_frame, height=80)
        self.prog_monitor.configure(state="disabled")
        self.prog_monitor.pack(fill="both", expand=True, padx=5, pady=5)

        # 6. Footer Info & Theme Control
        footer_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        footer_frame.pack(fill="x", padx=5, pady=(2, 4))

        ctk.CTkLabel(
            footer_frame,
            text="More info: GitHub.com/JimHeaney/ESP-Config",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"),
        ).pack(side="left")

        footer_right = ctk.CTkFrame(footer_frame, fg_color="transparent")
        footer_right.pack(side="right")

        ctk.CTkLabel(
            footer_right,
            text="V1.0.0",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=("gray40", "gray60"),
        ).pack(side="right", padx=(8, 0))

        self.theme_dropdown = ctk.CTkOptionMenu(
            footer_right,
            values=["System", "Dark", "Light"],
            width=90,
            height=22,
            font=ctk.CTkFont(size=11),
            command=self.change_theme_mode,
        )
        self.theme_dropdown.set("System")
        self.theme_dropdown.pack(side="right")

        ctk.CTkLabel(
            footer_right,
            text="Theme:",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"),
        ).pack(side="right", padx=(0, 4))

    def parse_macros(self, text, default_color=None):
        if text is None:
            return "", default_color or ("gray10", "gray90")
        text_str = str(text)
        color = default_color or ("gray10", "gray90")

        if "[bad]" in text_str:
            color = ("#DC2626", "#F87171")
            text_str = text_str.replace("[bad]", "")
        elif "[good]" in text_str:
            color = ("#059669", "#34D399")
            text_str = text_str.replace("[good]", "")

        if "[time]" in text_str:
            now_str = datetime.now().strftime("%H:%M:%S")
            text_str = text_str.replace("[time]", now_str)

        return text_str, color

    def safe_int(self, val):
        if val is None or val == "":
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    def build_limit_str(self, q_type, max_len, lower_lim, upper_lim):
        limits = []
        if q_type == "string" and max_len is not None:
            limits.append(f"Max length: {max_len}")
        elif q_type == "integer":
            if lower_lim is not None and upper_lim is not None:
                limits.append(f"Range: {lower_lim} to {upper_lim}")
            elif lower_lim is not None:
                limits.append(f"Min: {lower_lim}")
            elif upper_lim is not None:
                limits.append(f"Max: {upper_lim}")
        return f" ({', '.join(limits)})" if limits else ""

    def request_resend(self, missing_nums):
        for num in missing_nums:
            self.log_to_prog(f"-> Requesting resend of missed payload #{num}...")
            resend_payload = {"operation": "resend", "message-number": num}
            self.send_payload(resend_payload)

    def set_item_unavailable_state(self, item_key, is_unavail):
        item = self.rendered_items.get(item_key)
        if not item:
            return

        item["is_unavailable"] = is_unavail
        badge = item.get("unavail_badge")
        new_state = "disabled" if is_unavail else "normal"

        if is_unavail:
            if badge:
                badge.pack(side="left", padx=(5, 0))
            if "prompt_label" in item:
                item["prompt_label"].configure(text_color=("gray50", "gray50"))
            if "title_label" in item:
                item["title_label"].configure(text_color=("gray50", "gray50"))
        else:
            if badge:
                badge.pack_forget()
            if "prompt_label" in item:
                col = item.get("prompt_col") or ("gray10", "gray90")
                item["prompt_label"].configure(text_color=col)
            if "title_label" in item:
                col = item.get("title_col") or ("gray10", "gray90")
                item["title_label"].configure(text_color=col)

        if "entry" in item and item["entry"]:
            if isinstance(item["entry"], (ctk.CTkComboBox, ctk.CTkEntry)):
                item["entry"].configure(state=new_state)
        if "widget" in item and hasattr(item["widget"], "configure"):
            item["widget"].configure(state=new_state)

        for opt_w in item.get("option_widgets", []):
            opt_w.configure(state=new_state)

    def apply_filter(self):
        query = self.search_var.get().strip().lower()

        for item_key, item in self.rendered_items.items():
            container = item.get("container_frame")
            if not container or not container.winfo_exists():
                continue

            searchable_texts = [
                str(item.get("id", "")),
                str(item.get("source", "")),
                str(item.get("category", "")),
                str(item.get("title", "")),
                str(item.get("prompt", "")),
                str(item.get("message", "")),
                str(item.get("popup", "")),
                str(item.get("original_val", "")),
                str(item.get("q_type", "")),
                " ".join([str(o) for o in item.get("options", [])]),
            ]

            if (
                "entry" in item
                and item["entry"]
                and hasattr(item["entry"], "get")
                and not isinstance(item["entry"], ctk.StringVar)
            ):
                try:
                    searchable_texts.append(item["entry"].get())
                except Exception:
                    pass
            if "check_vars" in item:
                searchable_texts.extend(
                    [opt for opt, var in item["check_vars"].items() if var.get()]
                )

            combined_text = " ".join(searchable_texts).lower()
            match = (query in combined_text) if query else True
            item["visible_by_search"] = match

            if match:
                container.pack(fill="x", pady=3)
            else:
                container.pack_forget()

        self.update_structure_visibility()

    def update_structure_visibility(self):
        first_enabled_cat = None
        current_cat = self.notebook.get()
        current_cat_is_enabled = False

        for cat, tab_info in self.tabs.items():
            cat_has_visible_items = False

            for sec_type in ["information", "commands", "settings"]:
                sec_has_visible = False
                source_dict = tab_info["source_frames"][sec_type]

                for source_name, source_frame in source_dict.items():
                    has_visible_child = False
                    for item in self.rendered_items.values():
                        item_src = str(item.get("source", "Core")).strip() or "Core"
                        if (
                            item.get("category") == cat
                            and item.get("sec_type") == sec_type
                            and item_src == source_name
                            and item.get("visible_by_search", True)
                        ):
                            has_visible_child = True
                            break

                    # Only update layout geometry if frame visibility state changed
                    if has_visible_child:
                        if not source_frame.winfo_ismapped():
                            source_frame.pack(fill="x", pady=4)
                        sec_has_visible = True
                    else:
                        if source_frame.winfo_ismapped():
                            source_frame.pack_forget()

                section = tab_info["sections"][sec_type]
                if sec_has_visible and tab_info["has_items"][sec_type]:
                    if not section.winfo_ismapped():
                        section.pack(fill="x", pady=4, anchor="n")
                    cat_has_visible_items = True
                else:
                    if section.winfo_ismapped():
                        section.pack_forget()

            # Enable or grey out tab button only if state differs from current
            btn = self.notebook._segmented_button._buttons_dict.get(cat)
            if btn:
                target_state = "normal" if cat_has_visible_items else "disabled"
                if btn.cget("state") != target_state:
                    btn.configure(state=target_state)

                if cat_has_visible_items:
                    if first_enabled_cat is None:
                        first_enabled_cat = cat
                    if cat == current_cat:
                        current_cat_is_enabled = True

        # Automatically switch tab only if current active tab became disabled
        if not current_cat_is_enabled and first_enabled_cat:
            self.notebook.set(first_enabled_cat)

    def toggle_config_visibility(self):
        self.show_config_messages = self.show_config_var.get()
        self.hide_ack_messages = self.hide_ack_var.get()

        if self.show_config_messages:
            self.hide_ack_chk.configure(state="normal")
        else:
            self.hide_ack_chk.configure(state="disabled")

    def refresh_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_cb.configure(values=ports)
        if ports:
            self.port_cb.set(ports[0])

    def log_to_monitor(self, text):
        self.monitor.configure(state="normal")
        self.monitor.insert("end", text + "\n")
        self.monitor.see("end")
        self.monitor.configure(state="disabled")

    def log_to_prog(self, text):
        self.prog_monitor.configure(state="normal")
        self.prog_monitor.insert("end", text + "\n")
        self.prog_monitor.see("end")
        self.prog_monitor.configure(state="disabled")

    def set_password(self):
        self.current_password = self.pass_entry.get()
        self.pass_status.configure(
            text="Status: Sending...", text_color=("orange", "#F59E0B")
        )
        self.log_to_prog(
            "-> Password updated. Transmitting password payload immediately..."
        )
        self.send_payload({})

    def calculate_hash(self, payload_dict):
        payload_copy = json.loads(json.dumps(payload_dict))
        if "metadata" in payload_copy:
            payload_copy["metadata"]["hash"] = "0"
        json_bytes = json.dumps(payload_copy, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(json_bytes).hexdigest()

    def create_metadata(self):
        meta = {
            "hash": "0",
            "version": 1,
            "message-number": self.tx_message_number,
        }
        if self.current_password:
            meta["password"] = self.current_password
        self.tx_message_number += 1
        return meta

    def send_payload(self, payload_dict):
        if not (self.is_connected and self.serial_port and self.serial_port.is_open):
            self.log_to_prog("Error: Cannot send payload (Not connected).")
            return

        payload_dict["metadata"] = self.create_metadata()
        payload_dict["metadata"]["hash"] = self.calculate_hash(payload_dict)

        json_msg = json.dumps(payload_dict) + "\n"
        try:
            self.serial_port.write(json_msg.encode("utf-8"))
            self.log_to_prog(f"-> Sent: {json_msg.strip()}")
            if self.current_password:
                self.pass_status.configure(
                    text="Status: Sent", text_color=("#1D4ED8", "#60A5FA")
                )
        except Exception as e:
            self.log_to_prog(f"Error sending payload: {e}")

    def send_answers(self, category):
        answers = []
        for item_key, item in self.rendered_items.items():
            if item.get("type") == "question" and item.get("category") == category:
                if item.get("is_unavailable"):
                    continue

                item_id = item.get("id")
                q_type = item.get("q_type", "string")
                max_len = item.get("max_length")
                upper_lim = item.get("upper_limit")
                lower_lim = item.get("lower_limit")
                options = item.get("options", [])

                if q_type == "selection":
                    check_vars = item.get("check_vars", {})
                    val = [opt for opt, var in check_vars.items() if var.get()]

                elif q_type == "choice":
                    val = item["entry"].get()
                    if options and val not in options:
                        msg = f"Selection for '{item_id}' ({val}) is not a valid option."
                        messagebox.showwarning("Invalid Choice", msg)
                        self.log_to_prog(f"Error: {msg}")
                        return

                elif q_type == "integer":
                    raw_val = item["entry"].get()
                    try:
                        val = int(raw_val)
                    except ValueError:
                        msg = f"Value for '{item_id}' must be a valid integer."
                        messagebox.showwarning("Validation Error", msg)
                        self.log_to_prog(f"Error: {msg}")
                        return

                    if lower_lim is not None and val < lower_lim:
                        msg = f"Value for '{item_id}' ({val}) is below minimum limit ({lower_lim})."
                        messagebox.showwarning("Out of Bounds", msg)
                        self.log_to_prog(f"Error: {msg}")
                        return

                    if upper_lim is not None and val > upper_lim:
                        msg = f"Value for '{item_id}' ({val}) exceeds maximum limit ({upper_lim})."
                        messagebox.showwarning("Out of Bounds", msg)
                        self.log_to_prog(f"Error: {msg}")
                        return

                elif q_type == "string":
                    val = item["entry"].get()
                    if max_len is not None and len(val) > max_len:
                        msg = f"Value for '{item_id}' length ({len(val)}) exceeds max length ({max_len})."
                        messagebox.showwarning("Out of Bounds", msg)
                        self.log_to_prog(f"Error: {msg}")
                        return
                else:
                    val = item["entry"].get()

                ans_obj = {"id": item_id, "answer": val}
                if item.get("source"):
                    ans_obj["source"] = item["source"]

                answers.append(ans_obj)
                item["original_val"] = val

        if answers:
            payload = {"answers": answers}
            self.send_payload(payload)
        else:
            self.log_to_prog(f"No answers found to send for category '{category}'.")

    def discard_answers(self, category):
        count = 0
        for item_key, item in self.rendered_items.items():
            if item.get("type") == "question" and item.get("category") == category:
                if not item.get("is_unavailable"):
                    q_type = item.get("q_type")
                    orig = item.get("original_val")

                    if q_type == "selection":
                        orig_list = (
                            orig if isinstance(orig, list) else ([orig] if orig else [])
                        )
                        for opt, var in item.get("check_vars", {}).items():
                            var.set(opt in orig_list)
                    elif q_type == "choice":
                        item["entry"].set(str(orig))
                    else:
                        item["entry"].delete(0, "end")
                        item["entry"].insert(0, str(orig))
                    count += 1
        self.log_to_prog(
            f"Discarded changes for {count} answer(s) in category '{category}'."
        )

    def send_command(self, item_key, input_val):
        item = self.rendered_items.get(item_key, {})
        if item.get("is_unavailable"):
            return

        item_id = item.get(
            "id", item_key[1] if isinstance(item_key, tuple) else item_key
        )
        max_len = item.get("max_length")

        if isinstance(input_val, str) and max_len is not None:
            if len(input_val) > max_len:
                msg = f"Command input length ({len(input_val)}) exceeds max length ({max_len})."
                messagebox.showwarning("Out of Bounds", msg)
                self.log_to_prog(f"Error: {msg}")
                return

        cmd_obj = {"id": item_id, "input": input_val}
        if item.get("source"):
            cmd_obj["source"] = item["source"]

        payload = {"commands": [cmd_obj]}
        self.send_payload(payload)

    def toggle_connection(self):
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()

    def check_connection_timeout(self, port):
        if self.is_connected and not self.handshake_received:
            self.log_to_prog(f"Error: Connection timeout. No device found on {port}.")
            self.disconnect()
            messagebox.showerror(
                "Connection Failed",
                f"No responsive ESP-Config device was found on {port}.",
            )
        elif self.is_connected and self.handshake_received:
            self.send_keep_alive()

    def connect(self):
        port = self.port_cb.get()
        if not port:
            return
        try:
            self.serial_port = serial.Serial(port, 115200, timeout=1)
            self.is_connected = True
            self.handshake_received = False
            self.tx_message_number = 0
            self.last_rx_message_num = 0
            self.received_msg_numbers.clear()
            self.highest_contiguous_rx = 0

            self.connect_btn.configure(
                text="Disconnect", fg_color="#DC2626", hover_color="#B91C1C"
            )
            self.log_to_prog(f"--- Connecting to {port}... ---")

            self.read_thread = threading.Thread(target=self.read_from_port, daemon=True)
            self.read_thread.start()

            start_payload = json.dumps({"operation": "start"}) + "\n"
            self.serial_port.write(start_payload.encode("utf-8"))

            # Schedule a 5-second connection handshake check
            self.root.after(5000, lambda: self.check_connection_timeout(port))

        except Exception as e:
            self.log_to_prog(f"Error connecting: {e}")
            self.disconnect()

    def send_keep_alive(self):
        if self.is_connected and self.serial_port and self.serial_port.is_open:
            try:
                check_payload = (
                    json.dumps(
                        {
                            "operation": "check",
                            "last": self.highest_contiguous_rx,
                        }
                    )
                    + "\n"
                )
                self.serial_port.write(check_payload.encode("utf-8"))
            except Exception as e:
                self.log_to_prog(f"Error sending keep-alive: {e}")

            self.root.after(1000, self.send_keep_alive)

    def disconnect(self):
        self.is_connected = False
        self.handshake_received = False
        if self.serial_port and self.serial_port.is_open:
            try:
                end_payload = json.dumps({"operation": "end"}) + "\n"
                self.serial_port.write(end_payload.encode("utf-8"))
                self.serial_port.close()
            except Exception:
                pass

        self.connect_btn.configure(
            text="Connect", fg_color="#10B981", hover_color="#059669"
        )
        self.log_to_prog("--- Disconnected ---")

        self.current_password = ""
        self.pass_entry.delete(0, "end")
        self.pass_status.configure(
            text="Status: Not Set", text_color=("gray40", "gray60")
        )
        self.pass_hint.configure(
            text="Hint: (Waiting for device...)", text_color=("#1D4ED8", "#60A5FA")
        )
        if not self.pass_frame.winfo_ismapped():
            self.pass_frame.pack(pady=5, padx=5, fill="x", before=self.notebook)

        self.received_msg_numbers.clear()
        self.highest_contiguous_rx = 0
        self.last_rx_message_num = 0

        for tab_dict in self.tabs.values():
            try:
                self.notebook.delete(tab_dict["cat_name"])
            except Exception:
                pass
        self.tabs.clear()
        self.rendered_items.clear()

    def on_closing(self):
        if self.is_connected:
            self.disconnect()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.destroy()

    def read_from_port(self):
        while self.is_connected and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting > 0:
                    line = (
                        self.serial_port.readline()
                        .decode("utf-8", errors="ignore")
                        .strip()
                    )
                    if not line:
                        continue

                    if line.startswith("[config]"):
                        self.handshake_received = True
                        json_start = line.find("{")
                        payload = None
                        if json_start != -1:
                            json_str = line[json_start:]
                            try:
                                payload = json.loads(json_str)
                            except json.JSONDecodeError:
                                pass

                        is_ack = False
                        if payload and isinstance(payload, dict):
                            if (
                                payload.get("operation") == "ack"
                                or payload.get("type") == "ack"
                                or "ack" in payload
                            ):
                                is_ack = True
                        elif "ack" in line.lower():
                            is_ack = True

                        if self.show_config_messages:
                            if not (self.hide_ack_messages and is_ack):
                                self.root.after(0, self.log_to_monitor, line)

                        if json_start != -1:
                            if payload is not None:
                                self.root.after(
                                    0, self.update_gui_with_payload, payload
                                )
                            else:
                                self.root.after(
                                    0,
                                    self.log_to_prog,
                                    "Error: Received malformed JSON configuration.",
                                )
                        else:
                            self.root.after(
                                0,
                                self.log_to_prog,
                                "Error: Missing JSON body in config payload.",
                            )
                    else:
                        self.root.after(0, self.log_to_monitor, line)
            except Exception as e:
                if self.is_connected:
                    self.root.after(0, self.log_to_prog, f"Serial read error: {e}")
                break

    def ensure_category_tab(self, category):
        if category in self.tabs:
            return

        tab_root = self.notebook.add(category)
        scrollable_frame = ctk.CTkScrollableFrame(tab_root)
        scrollable_frame.pack(fill="both", expand=True)

        info_sec = CollapsibleSection(scrollable_frame, title="Information")
        cmd_sec = CollapsibleSection(scrollable_frame, title="Commands")
        settings_sec = CollapsibleSection(scrollable_frame, title="Settings")

        # Pack header extras frame specifically for settings controls
        settings_sec.header_extras.pack(side="right", padx=4)

        send_answers_btn = ctk.CTkButton(
            settings_sec.header_extras,
            text="Send Answers",
            width=90,
            height=24,
            text_color="white",
            command=lambda cat=category: self.send_answers(cat),
        )
        send_answers_btn.pack(side="left", padx=2)

        discard_answers_btn = ctk.CTkButton(
            settings_sec.header_extras,
            text="Discard Answers",
            width=90,
            height=24,
            fg_color=("gray70", "gray35"),
            hover_color=("gray60", "gray45"),
            text_color="white",
            command=lambda cat=category: self.discard_answers(cat),
        )
        discard_answers_btn.pack(side="left", padx=2)

        info_sec.pack_forget()
        cmd_sec.pack_forget()
        settings_sec.pack_forget()

        self.tabs[category] = {
            "cat_name": category,
            "tab_root": tab_root,
            "sections": {
                "information": info_sec,
                "commands": cmd_sec,
                "settings": settings_sec,
            },
            "source_frames": {
                "information": {},
                "commands": {},
                "settings": {},
            },
            "has_items": {
                "information": False,
                "commands": False,
                "settings": False,
            },
        }

    def get_source_frame(self, category, sec_type, source):
        source_name = (
            str(source).strip() if source and str(source).strip() else "Core"
        )
        section_frame = self.tabs[category]["sections"][sec_type].content_frame
        source_dict = self.tabs[category]["source_frames"][sec_type]

        if source_name not in source_dict:
            lf = ctk.CTkFrame(section_frame, fg_color=("gray90", "gray20"))
            lf.pack(fill="x", pady=4)

            lbl = ctk.CTkLabel(
                lf,
                text=f" {source_name} ",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=("gray20", "gray80"),
            )
            lbl.pack(anchor="w", padx=5, pady=(4, 2))

            source_dict[source_name] = lf

        return source_dict[source_name]

    def show_section(self, category, sec_type):
        tab_info = self.tabs[category]
        if not tab_info["has_items"][sec_type]:
            tab_info["has_items"][sec_type] = True
            for key in ["information", "commands", "settings"]:
                if tab_info["has_items"][key]:
                    tab_info["sections"][key].pack(
                        fill="x", pady=4, anchor="n"
                    )

    def update_gui_with_payload(self, payload):
        if "metadata" in payload:
            meta = payload["metadata"]

            if "message-number" in meta:
                rx_num = meta["message-number"]

                if rx_num not in self.received_msg_numbers:
                    self.received_msg_numbers.add(rx_num)

                    if (
                        self.last_rx_message_num > 0
                        and rx_num > self.last_rx_message_num + 1
                    ):
                        missing = [
                            n
                            for n in range(self.last_rx_message_num + 1, rx_num)
                            if n not in self.received_msg_numbers
                        ]
                        if missing:
                            self.log_to_prog(
                                f"Sequence gap! Expected {self.last_rx_message_num + 1},"
                                f" received {rx_num}. Missing: {missing}"
                            )
                            self.request_resend(missing)

                    while (
                        self.highest_contiguous_rx + 1
                    ) in self.received_msg_numbers:
                        self.highest_contiguous_rx += 1

                    if rx_num > self.last_rx_message_num:
                        self.last_rx_message_num = rx_num

            if "hint" in meta:
                hint_clean, hint_col = self.parse_macros(
                    f"Hint: {meta['hint']}",
                    default_color=("#1D4ED8", "#60A5FA"),
                )
                self.pass_hint.configure(text=hint_clean, text_color=hint_col)

            if "password-correct" in meta:
                if meta["password-correct"]:
                    self.pass_status.configure(
                        text="Status: Correct", text_color=("#059669", "#34D399")
                    )
                    self.pass_frame.pack_forget()
                else:
                    if not self.pass_frame.winfo_ismapped():
                        self.pass_frame.pack(
                            pady=5, padx=5, fill="x", before=self.notebook
                        )
                    self.pass_status.configure(
                        text="Status: Incorrect", text_color=("#DC2626", "#F87171")
                    )

        if "information" in payload:
            for info in payload["information"]:
                item_id = info.get("id")
                source = info.get("source", "Core")
                item_key = (source, item_id)
                raw_cat = info.get("category")

                if item_key in self.rendered_items:
                    if "value" in info:
                        val_clean, val_col = self.parse_macros(
                            info.get("value", "")
                        )
                        self.rendered_items[item_key]["value_label"].configure(
                            text=val_clean, text_color=val_col
                        )
                    continue

                if not raw_cat or not str(raw_cat).strip():
                    self.log_to_prog(
                        f"Ignored info item '{item_id}' from source '{source}':"
                        " Unrecognized item and missing category."
                    )
                    continue

                category = str(raw_cat).strip()
                self.ensure_category_tab(category)
                self.show_section(category, "information")

                target_frame = self.get_source_frame(category, "information", source)
                container = ctk.CTkFrame(target_frame, fg_color="transparent")
                container.pack(fill="x", pady=3)

                row_frame = ctk.CTkFrame(container, fg_color="transparent")
                row_frame.pack(fill="x")

                title_clean, title_col = self.parse_macros(
                    info.get("title", "Info")
                )
                title_label = ctk.CTkLabel(
                    row_frame,
                    text=f"{title_clean}: ",
                    font=ctk.CTkFont(weight="bold"),
                    text_color=title_col,
                )
                title_label.pack(side="left", padx=4)

                val_clean, val_col = self.parse_macros(info.get("value", ""))
                value_label = ctk.CTkLabel(
                    row_frame, text=val_clean, text_color=val_col
                )
                value_label.pack(side="left")

                popup_raw = info.get("pop-up", "") or info.get("explanation", "")
                popup_text, _ = self.parse_macros(popup_raw)
                if popup_text:
                    help_label = ctk.CTkLabel(
                        row_frame,
                        text=" [?] ",
                        text_color=("#1D4ED8", "#60A5FA"),
                        font=ctk.CTkFont(size=11, weight="bold"),
                        cursor="hand2",
                    )
                    help_label.pack(side="left")
                    help_label.tooltip = ToolTip(help_label, popup_text)

                self.rendered_items[item_key] = {
                    "id": item_id,
                    "type": "info",
                    "sec_type": "information",
                    "source": source,
                    "category": category,
                    "title": title_clean,
                    "container_frame": container,
                    "row_frame": row_frame,
                    "title_label": title_label,
                    "title_col": title_col,
                    "value_label": value_label,
                    "popup": popup_text,
                    "visible_by_search": True,
                }

        if "questions" in payload:
            for q in payload["questions"]:
                item_id = q.get("id")
                source = q.get("source", "Core")
                item_key = (source, item_id)
                raw_cat = q.get("category")

                if item_key in self.rendered_items:
                    item_ref = self.rendered_items[item_key]

                    if "options" in q and q["options"] != item_ref.get("options"):
                        new_opts = q["options"]
                        item_ref["options"] = new_opts
                        q_type = item_ref.get("q_type")

                        if (
                            q_type == "choice"
                            and isinstance(item_ref.get("entry"), ctk.CTkComboBox)
                            and len(new_opts) > 4
                        ):
                            item_ref["entry"].configure(values=new_opts)
                        else:
                            for opt_w in item_ref.get("option_widgets", []):
                                opt_w.destroy()
                            item_ref["option_widgets"] = []

                            if (
                                "opt_frame" in item_ref
                                and item_ref["opt_frame"]
                                and item_ref["opt_frame"].winfo_exists()
                            ):
                                item_ref["opt_frame"].destroy()
                                item_ref["opt_frame"] = None

                            if isinstance(item_ref.get("entry"), ctk.CTkComboBox):
                                item_ref["entry"].destroy()
                                item_ref["entry"] = None

                            row_frame = item_ref["row_frame"]
                            current_val = q.get(
                                "current", item_ref.get("original_val", "")
                            )

                            if q_type == "selection":
                                curr_list = (
                                    current_val
                                    if isinstance(current_val, list)
                                    else ([current_val] if current_val else [])
                                )
                                item_ref["check_vars"] = {}

                                opt_frame = ctk.CTkFrame(
                                    row_frame, fg_color="transparent"
                                )
                                opt_frame.pack(side="left", padx=5)
                                item_ref["opt_frame"] = opt_frame

                                for opt in new_opts:
                                    var = ctk.BooleanVar(value=(opt in curr_list))
                                    cb = ctk.CTkCheckBox(
                                        opt_frame, text=opt, variable=var
                                    )
                                    cb.pack(side="left", padx=4)
                                    item_ref["check_vars"][opt] = var
                                    item_ref["option_widgets"].append(cb)

                            elif q_type == "choice":
                                if len(new_opts) <= 4 and new_opts:
                                    opt_frame = ctk.CTkFrame(
                                        row_frame, fg_color="transparent"
                                    )
                                    opt_frame.pack(side="left", padx=5)
                                    item_ref["opt_frame"] = opt_frame
                                    radio_var = ctk.StringVar(value=str(current_val))

                                    for opt in new_opts:
                                        rb = ctk.CTkRadioButton(
                                            opt_frame,
                                            text=opt,
                                            value=opt,
                                            variable=radio_var,
                                        )
                                        rb.pack(side="left", padx=4)
                                        item_ref["option_widgets"].append(rb)
                                    item_ref["entry"] = radio_var
                                else:
                                    entry_widget = ctk.CTkComboBox(
                                        row_frame, values=new_opts
                                    )
                                    str_curr = str(current_val)
                                    entry_widget.set(
                                        str_curr
                                        if str_curr in new_opts
                                        else (new_opts[0] if new_opts else "")
                                    )
                                    entry_widget.pack(
                                        side="left", padx=5, fill="x", expand=True
                                    )
                                    item_ref["entry"] = entry_widget

                    if "message" in q:
                        msg_clean, msg_col = self.parse_macros(
                            q.get("message", ""), default_color=("gray40", "gray60")
                        )
                        item_ref["msg_label"].configure(
                            text=msg_clean, text_color=msg_col
                        )
                        if msg_clean:
                            item_ref["msg_label"].pack(fill="x", padx=(10, 0))
                        else:
                            item_ref["msg_label"].pack_forget()
                        item_ref["message"] = msg_clean

                    if "current" in q:
                        new_curr = q.get("current", "")
                        item_ref["original_val"] = new_curr
                        if item_ref.get("q_type") == "selection":
                            curr_list = (
                                new_curr
                                if isinstance(new_curr, list)
                                else ([new_curr] if new_curr else [])
                            )
                            for opt, var in item_ref.get("check_vars", {}).items():
                                var.set(opt in curr_list)
                        elif item_ref.get("q_type") == "choice":
                            if isinstance(
                                item_ref.get("entry"), (ctk.CTkComboBox, ctk.StringVar)
                            ):
                                item_ref["entry"].set(str(new_curr))
                        else:
                            item_ref["entry"].delete(0, "end")
                            item_ref["entry"].insert(0, str(new_curr))

                    if "unavailable" in q:
                        is_unavail = bool(q.get("unavailable"))
                        self.set_item_unavailable_state(item_key, is_unavail)
                    continue

                if not raw_cat or not str(raw_cat).strip():
                    self.log_to_prog(
                        f"Ignored question item '{item_id}' from source '{source}':"
                        " Unrecognized item and missing category."
                    )
                    continue

                category = str(raw_cat).strip()
                q_type = q.get("type", "string")
                max_len = self.safe_int(q.get("max-length"))
                lower_lim = self.safe_int(q.get("lower-limit"))
                upper_lim = self.safe_int(q.get("upper-limit"))
                options = (
                    q.get("options", []) if q_type in ["choice", "selection"] else []
                )
                is_unavail = bool(q.get("unavailable", False))

                self.ensure_category_tab(category)
                self.show_section(category, "settings")

                target_frame = self.get_source_frame(category, "settings", source)
                q_container = ctk.CTkFrame(target_frame, fg_color="transparent")
                q_container.pack(fill="x", pady=3)

                row_frame = ctk.CTkFrame(q_container, fg_color="transparent")
                row_frame.pack(fill="x")

                limit_str = self.build_limit_str(q_type, max_len, lower_lim, upper_lim)
                prompt_clean, prompt_col = self.parse_macros(
                    q.get("prompt", "Question:")
                )
                prompt_text = f"{prompt_clean}{limit_str}"

                prompt_label = ctk.CTkLabel(
                    row_frame, text=prompt_text, text_color=prompt_col
                )
                prompt_label.pack(side="left", padx=4)

                unavail_badge = ctk.CTkLabel(
                    row_frame,
                    text=" [UNAVAILABLE] ",
                    fg_color=("gray75", "gray30"),
                    text_color=("gray10", "gray90"),
                    font=ctk.CTkFont(size=9, weight="bold"),
                    corner_radius=4,
                )

                current_val = q.get("current", "")
                option_widgets = []
                check_vars = {}
                entry_widget = None
                opt_frame = None

                if q_type == "selection":
                    curr_list = (
                        current_val
                        if isinstance(current_val, list)
                        else ([current_val] if current_val else [])
                    )
                    opt_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
                    opt_frame.pack(side="left", padx=5)

                    for opt in options:
                        var = ctk.BooleanVar(value=(opt in curr_list))
                        cb = ctk.CTkCheckBox(opt_frame, text=opt, variable=var)
                        cb.pack(side="left", padx=4)
                        check_vars[opt] = var
                        option_widgets.append(cb)

                elif q_type == "choice":
                    if len(options) <= 4 and options:
                        opt_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
                        opt_frame.pack(side="left", padx=5)
                        radio_var = ctk.StringVar(value=str(current_val))

                        for opt in options:
                            rb = ctk.CTkRadioButton(
                                opt_frame,
                                text=opt,
                                value=opt,
                                variable=radio_var,
                            )
                            rb.pack(side="left", padx=4)
                            option_widgets.append(rb)
                        entry_widget = radio_var
                    else:
                        entry_widget = ctk.CTkComboBox(row_frame, values=options)
                        str_curr = str(current_val)
                        entry_widget.set(
                            str_curr
                            if str_curr in options
                            else (options[0] if options else "")
                        )
                        entry_widget.pack(side="left", padx=5, fill="x", expand=True)

                else:
                    entry_widget = ctk.CTkEntry(row_frame)
                    entry_widget.insert(0, str(current_val))
                    entry_widget.pack(side="left", padx=5, fill="x", expand=True)

                msg_clean, msg_col = self.parse_macros(
                    q.get("message", ""), default_color=("gray40", "gray60")
                )
                msg_label = ctk.CTkLabel(
                    q_container,
                    text=msg_clean,
                    text_color=msg_col,
                    anchor="w",
                    justify="left",
                    font=ctk.CTkFont(size=11, slant="italic"),
                )
                if msg_clean:
                    msg_label.pack(fill="x", padx=(10, 0))

                self.rendered_items[item_key] = {
                    "id": item_id,
                    "type": "question",
                    "sec_type": "settings",
                    "q_type": q_type,
                    "options": options,
                    "source": source,
                    "category": category,
                    "prompt": prompt_clean,
                    "message": msg_clean,
                    "max_length": max_len,
                    "upper_limit": upper_lim,
                    "lower_limit": lower_lim,
                    "container_frame": q_container,
                    "row_frame": row_frame,
                    "opt_frame": opt_frame,
                    "msg_label": msg_label,
                    "prompt_label": prompt_label,
                    "prompt_col": prompt_col,
                    "entry": entry_widget,
                    "check_vars": check_vars,
                    "option_widgets": option_widgets,
                    "original_val": current_val,
                    "unavail_badge": unavail_badge,
                    "is_unavailable": is_unavail,
                    "visible_by_search": True,
                }

                self.set_item_unavailable_state(item_key, is_unavail)

        if "commands" in payload:
            for cmd in payload["commands"]:
                item_id = cmd.get("id")
                source = cmd.get("source", "Core")
                item_key = (source, item_id)
                raw_cat = cmd.get("category")

                if item_key in self.rendered_items:
                    item_ref = self.rendered_items[item_key]
                    if "message" in cmd and "msg_label" in item_ref:
                        msg_clean, msg_col = self.parse_macros(
                            cmd.get("message", ""), default_color=("gray40", "gray60")
                        )
                        item_ref["msg_label"].configure(
                            text=msg_clean, text_color=msg_col
                        )
                        if msg_clean:
                            item_ref["msg_label"].pack(fill="x", padx=(10, 0))
                        else:
                            item_ref["msg_label"].pack_forget()
                        item_ref["message"] = msg_clean
                    if "pop-up" in cmd:
                        popup_clean, _ = self.parse_macros(cmd.get("pop-up"))
                        item_ref["popup"] = popup_clean
                    if "unavailable" in cmd:
                        is_unavail = bool(cmd.get("unavailable"))
                        self.set_item_unavailable_state(item_key, is_unavail)
                    continue

                if not raw_cat or not str(raw_cat).strip():
                    self.log_to_prog(
                        f"Ignored command item '{item_id}' from source '{source}':"
                        " Unrecognized item and missing category."
                    )
                    continue

                category = str(raw_cat).strip()
                cmd_type = cmd.get("type", "button")
                popup_clean, _ = self.parse_macros(cmd.get("pop-up"))
                msg_clean, msg_col = self.parse_macros(
                    cmd.get("message", ""), default_color=("gray40", "gray60")
                )
                max_len = self.safe_int(cmd.get("max-length"))
                is_unavail = bool(cmd.get("unavailable", False))

                self.ensure_category_tab(category)
                self.show_section(category, "commands")

                target_frame = self.get_source_frame(category, "commands", source)
                cmd_container = ctk.CTkFrame(target_frame, fg_color="transparent")
                cmd_container.pack(fill="x", pady=3)

                row_frame = ctk.CTkFrame(cmd_container, fg_color="transparent")
                row_frame.pack(fill="x")

                unavail_badge = ctk.CTkLabel(
                    row_frame,
                    text=" [UNAVAILABLE] ",
                    fg_color=("gray75", "gray30"),
                    text_color=("gray10", "gray90"),
                    font=ctk.CTkFont(size=9, weight="bold"),
                    corner_radius=4,
                )

                if cmd_type in ["string", "text", "input"]:
                    title_raw = cmd.get("title", cmd.get("prompt", "Command:"))
                    title_clean, title_col = self.parse_macros(title_raw)
                    if max_len is not None:
                        title_clean += f" (Max length: {max_len})"

                    label = ctk.CTkLabel(
                        row_frame, text=title_clean + " ", text_color=title_col
                    )
                    label.pack(side="left", padx=4)

                    cmd_entry = ctk.CTkEntry(row_frame)
                    cmd_entry.insert(0, str(cmd.get("current", "")))
                    cmd_entry.pack(side="left", padx=5, fill="x", expand=True)

                    def on_send_string(c_key=item_key, entry_widget=cmd_entry):
                        p_text = self.rendered_items[c_key].get("popup")
                        if p_text and not messagebox.askokcancel(
                            "Confirm Command", p_text
                        ):
                            return
                        self.send_command(c_key, entry_widget.get())

                    send_btn = ctk.CTkButton(
                        row_frame,
                        text="Send",
                        width=50,
                        fg_color="#10B981",
                        hover_color="#059669",
                        text_color="white",
                        font=ctk.CTkFont(weight="bold"),
                        command=on_send_string,
                    )
                    send_btn.pack(side="left", padx=2)

                    msg_label = ctk.CTkLabel(
                        cmd_container,
                        text=msg_clean,
                        text_color=msg_col,
                        anchor="w",
                        justify="left",
                        font=ctk.CTkFont(size=11, slant="italic"),
                    )
                    if msg_clean:
                        msg_label.pack(fill="x", padx=(10, 0))

                    self.rendered_items[item_key] = {
                        "id": item_id,
                        "type": "command",
                        "sec_type": "commands",
                        "source": source,
                        "category": category,
                        "title": title_clean,
                        "message": msg_clean,
                        "max_length": max_len,
                        "container_frame": cmd_container,
                        "row_frame": row_frame,
                        "title_label": label,
                        "title_col": title_col,
                        "widget": send_btn,
                        "entry": cmd_entry,
                        "popup": popup_clean,
                        "msg_label": msg_label,
                        "unavail_badge": unavail_badge,
                        "is_unavailable": is_unavail,
                        "visible_by_search": True,
                    }

                elif cmd_type == "latch":
                    title_clean, title_col = self.parse_macros(
                        cmd.get("title", "Command"), default_color="white"
                    )
                    initial_latched = bool(cmd.get("current", False))

                    btn = ctk.CTkButton(
                        row_frame,
                        text=title_clean,
                        text_color="white",
                        fg_color="#10B981" if initial_latched else None,
                    )
                    btn.pack(side="left", padx=4)

                    def toggle_latch(c_key=item_key, b=btn):
                        item_ref = self.rendered_items[c_key]
                        if item_ref.get("is_unavailable"):
                            return
                        p_text = item_ref.get("popup")
                        if p_text and not messagebox.askokcancel(
                            "Confirm Command", p_text
                        ):
                            return

                        new_state = not item_ref.get("is_latched", False)
                        item_ref["is_latched"] = new_state
                        b.configure(fg_color="#10B981" if new_state else "#3B82F6")

                        self.send_command(c_key, new_state)

                    btn.configure(command=toggle_latch)

                    msg_label = ctk.CTkLabel(
                        cmd_container,
                        text=msg_clean,
                        text_color=msg_col,
                        anchor="w",
                        justify="left",
                        font=ctk.CTkFont(size=11, slant="italic"),
                    )
                    if msg_clean:
                        msg_label.pack(fill="x", padx=(10, 0))

                    self.rendered_items[item_key] = {
                        "id": item_id,
                        "type": "command",
                        "sec_type": "commands",
                        "source": source,
                        "category": category,
                        "title": title_clean,
                        "message": msg_clean,
                        "container_frame": cmd_container,
                        "row_frame": row_frame,
                        "title_label": btn,
                        "title_col": title_col,
                        "widget": btn,
                        "popup": popup_clean,
                        "is_latched": initial_latched,
                        "msg_label": msg_label,
                        "unavail_badge": unavail_badge,
                        "is_unavailable": is_unavail,
                        "visible_by_search": True,
                    }

                else:
                    title_clean, title_col = self.parse_macros(
                        cmd.get("title", "Command"), default_color="white"
                    )
                    btn = ctk.CTkButton(
                        row_frame, text=title_clean, text_color="white"
                    )
                    btn.pack(side="left", padx=4)

                    def handle_popup_btn(c_key=item_key, b=btn):
                        p_text = self.rendered_items[c_key].get("popup")
                        confirmed = (
                            messagebox.askokcancel("Confirm Command", p_text)
                            if p_text
                            else True
                        )
                        cmd_state = (
                            "disabled"
                            if self.rendered_items[c_key].get("is_unavailable")
                            else "normal"
                        )
                        b.configure(state=cmd_state)
                        if confirmed:
                            self.send_command(c_key, True)
                            self.send_command(c_key, False)

                    def on_press(e, c_key=item_key, b=btn):
                        if self.rendered_items[c_key].get("is_unavailable"):
                            return
                        p_text = self.rendered_items[c_key].get("popup")
                        if p_text:
                            self.root.after(10, lambda: handle_popup_btn(c_key, b))
                        else:
                            self.send_command(c_key, True)

                    def on_release(e, c_key=item_key, b=btn):
                        if self.rendered_items[c_key].get("is_unavailable"):
                            return
                        p_text = self.rendered_items[c_key].get("popup")
                        if not p_text:
                            self.send_command(c_key, False)
                            cmd_state = (
                                "disabled"
                                if self.rendered_items[c_key].get("is_unavailable")
                                else "normal"
                            )
                            b.configure(state=cmd_state)

                    btn.bind("<ButtonPress-1>", on_press)
                    btn.bind("<ButtonRelease-1>", on_release)

                    msg_label = ctk.CTkLabel(
                        cmd_container,
                        text=msg_clean,
                        text_color=msg_col,
                        anchor="w",
                        justify="left",
                        font=ctk.CTkFont(size=11, slant="italic"),
                    )
                    if msg_clean:
                        msg_label.pack(fill="x", padx=(10, 0))

                    self.rendered_items[item_key] = {
                        "id": item_id,
                        "type": "command",
                        "sec_type": "commands",
                        "source": source,
                        "category": category,
                        "title": title_clean,
                        "message": msg_clean,
                        "container_frame": cmd_container,
                        "row_frame": row_frame,
                        "title_label": btn,
                        "title_col": title_col,
                        "widget": btn,
                        "popup": popup_clean,
                        "msg_label": msg_label,
                        "unavail_badge": unavail_badge,
                        "is_unavailable": is_unavail,
                        "visible_by_search": True,
                    }

                self.set_item_unavailable_state(item_key, is_unavail)

        if self.search_var.get().strip():
            self.apply_filter()


if __name__ == "__main__":
    root = ctk.CTk()
    root.geometry("1000x900")
    app = ESPConfigApp(root)
    root.mainloop()