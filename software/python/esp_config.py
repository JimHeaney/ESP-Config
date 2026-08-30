import hashlib
import json
import os
import serial
import serial.tools.list_ports
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from PIL import Image
import pystray
from pystray import MenuItem as item


def get_asset_path(filename):
  """Get absolute path to resource, works for dev and for PyInstaller."""
  base_path = getattr(sys, '_MEIPASS', os.path.abspath('.'))
  return os.path.join(base_path, filename)


class ToolTip:

  def __init__(self, widget, text):
    self.widget = widget
    self.text = text
    self.tooltip_window = None
    self.widget.bind('<Enter>', self.show_tooltip)
    self.widget.bind('<Leave>', self.hide_tooltip)

  def show_tooltip(self, event=None):
    if self.tooltip_window or not self.text:
      return
    x = self.widget.winfo_rootx() + 25
    y = self.widget.winfo_rooty() + 20

    self.tooltip_window = tk.Toplevel(self.widget)
    self.tooltip_window.wm_overrideredirect(True)
    self.tooltip_window.wm_geometry(f'+{x}+{y}')

    label = tk.Label(
        self.tooltip_window,
        text=self.text,
        justify='left',
        background='#ffffe0',
        relief='solid',
        borderwidth=1,
        font=('tahoma', '9', 'normal'),
        padx=4,
        pady=2,
    )
    label.pack(ipadx=1)

  def hide_tooltip(self, event=None):
    if self.tooltip_window:
      self.tooltip_window.destroy()
      self.tooltip_window = None


class CollapsibleSection(tk.Frame):

  def __init__(self, parent, title='', **kwargs):
    super().__init__(parent, **kwargs)
    self.title = title
    self.is_expanded = True

    self.header_frame = tk.Frame(self, bg='#dcdcdc', relief=tk.RAISED, bd=1)
    self.header_frame.pack(fill=tk.X, expand=True)

    self.toggle_btn = tk.Button(
        self.header_frame,
        text=f'▼  {self.title}',
        font=('TkDefaultFont', 9, 'bold'),
        anchor='w',
        relief=tk.FLAT,
        bg='#dcdcdc',
        activebackground='#cfcfcf',
        command=self.toggle,
    )
    self.toggle_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4, pady=2)

    self.header_extras = tk.Frame(self.header_frame, bg='#dcdcdc')
    self.header_extras.pack(side=tk.RIGHT, padx=4)

    self.content_frame = tk.Frame(self, padx=5, pady=5)
    self.content_frame.pack(fill=tk.BOTH, expand=True)

  def toggle(self):
    if self.is_expanded:
      self.content_frame.pack_forget()
      self.toggle_btn.config(text=f'▶  {self.title}')
      self.is_expanded = False
    else:
      self.content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
      self.toggle_btn.config(text=f'▼  {self.title}')
      self.is_expanded = True


class ESPConfigApp:

  def __init__(self, root):
    self.root = root
    self.root.title('ESP-Config Tool')
    self.default_container_bg = self.root.cget('bg')
    self.serial_port = None
    self.is_connected = False
    self.current_password = ''
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

    self.default_btn_bg = None

    self.setup_ui()
    self.setup_window_and_tray_icon()
    self.refresh_ports()

    self.root.protocol('WM_DELETE_WINDOW', self.on_closing)

  def setup_window_and_tray_icon(self):
    icon_filename = 'app_icon.png'
    icon_path = get_asset_path(icon_filename)

    if os.path.exists(icon_path):
      # Set main Tkinter window title bar icon
      try:
        self.tk_icon = tk.PhotoImage(file=icon_path)
        self.root.iconphoto(True, self.tk_icon)
      except Exception as e:
        self.log_to_prog(f'Warning: Could not set window icon: {e}')

      # Set System Tray Icon using pystray
      try:
        pil_img = Image.open(icon_path)
        menu = pystray.Menu(
            item('Show App', self.show_window), item('Quit', self.on_closing)
        )
        self.tray_icon = pystray.Icon(
            'esp_config', pil_img, 'ESP-Config Tool', menu
        )
        self.tray_icon.run_detached()
      except Exception as e:
        self.log_to_prog(f'Warning: Could not initialize system tray: {e}')
    else:
      self.log_to_prog(
          f"Warning: Icon file '{icon_filename}' not found at path:"
          f' {icon_path}'
      )

  def show_window(self, icon=None, item=None):
    self.root.after(0, self.root.deiconify)
    self.root.after(0, self.root.lift)

  def setup_ui(self):
    # 1. Connection Controls & Top-Right Search Bar
    control_frame = tk.Frame(self.root)
    control_frame.pack(pady=5, padx=5, fill=tk.X)

    tk.Label(control_frame, text='COM Port:').pack(side=tk.LEFT)
    self.port_cb = ttk.Combobox(control_frame, width=12)
    self.port_cb.pack(side=tk.LEFT, padx=5)

    tk.Button(control_frame, text='Refresh', command=self.refresh_ports).pack(
        side=tk.LEFT, padx=2
    )
    self.connect_btn = tk.Button(
        control_frame, text='Connect', command=self.toggle_connection
    )
    self.connect_btn.pack(side=tk.LEFT, padx=2)
    self.default_btn_bg = self.connect_btn.cget('background')

    # Connection Tip Label
    tk.Label(
        control_frame,
        text=(
            "Tip: Don't see everything you expected? Disconnect & Reconnect to"
            ' re-populate list'
        ),
        font=('TkDefaultFont', 8, 'italic'),
        fg='#555555',
    ).pack(side=tk.LEFT, padx=10)

    # Top-Right Search Bar
    search_frame = tk.Frame(control_frame)
    search_frame.pack(side=tk.RIGHT, padx=5)

    tk.Label(
        search_frame, text='🔍 Search:', font=('TkDefaultFont', 9, 'bold')
    ).pack(side=tk.LEFT, padx=(0, 2))
    self.search_var = tk.StringVar()
    self.search_var.trace_add('write', lambda *args: self.apply_filter())
    self.search_entry = tk.Entry(
        search_frame, textvariable=self.search_var, width=18
    )
    self.search_entry.pack(side=tk.LEFT)

    # 2. Password Frame
    self.pass_frame = tk.Frame(self.root)
    self.pass_frame.pack(pady=5, padx=5, fill=tk.X)

    tk.Label(self.pass_frame, text='Password:').pack(side=tk.LEFT)
    self.pass_entry = tk.Entry(self.pass_frame, show='*', width=18)
    self.pass_entry.pack(side=tk.LEFT, padx=5)
    tk.Button(
        self.pass_frame, text='Set Password', command=self.set_password
    ).pack(side=tk.LEFT, padx=5)

    self.pass_status = tk.Label(
        self.pass_frame, text='Status: Not Set', fg='gray'
    )
    self.pass_status.pack(side=tk.LEFT, padx=10)

    self.pass_hint = tk.Label(
        self.pass_frame, text='Hint: (Waiting for device...)', fg='blue'
    )
    self.pass_hint.pack(side=tk.LEFT, padx=5)

    # 3. Dynamic Category Tabs
    self.notebook = ttk.Notebook(self.root)
    self.notebook.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)

    # 4. Serial Monitor (Device Output)
    monitor_frame = tk.Frame(self.root)
    monitor_frame.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)

    monitor_header = tk.Frame(monitor_frame)
    monitor_header.pack(fill=tk.X, anchor=tk.W)

    tk.Label(monitor_header, text='Serial Monitor (Device Output):').pack(
        side=tk.LEFT
    )

    self.show_config_var = tk.BooleanVar(value=False)
    self.show_config_chk = tk.Checkbutton(
        monitor_header,
        text='Show [config] Messages',
        variable=self.show_config_var,
        command=self.toggle_config_visibility,
    )
    self.show_config_chk.pack(side=tk.LEFT, padx=(15, 5))

    self.hide_ack_var = tk.BooleanVar(value=False)
    self.hide_ack_chk = tk.Checkbutton(
        monitor_header,
        text="Hide 'ack' Messages",
        variable=self.hide_ack_var,
        command=self.toggle_config_visibility,
        state=tk.DISABLED,
    )
    self.hide_ack_chk.pack(side=tk.LEFT, padx=5)

    self.monitor = tk.Text(
        monitor_frame, height=8, state=tk.DISABLED, bg='#f4f4f4', wrap=tk.WORD
    )
    scroll = tk.Scrollbar(monitor_frame, command=self.monitor.yview)
    self.monitor.configure(yscrollcommand=scroll.set)
    self.monitor.tag_configure('hanging_indent', lmargin1=0, lmargin2=30)
    self.monitor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)

    # 5. Program Monitor (Software Debug Output)
    prog_frame = tk.Frame(self.root)
    prog_frame.pack(pady=5, padx=5, fill=tk.BOTH)

    tk.Label(prog_frame, text='Program Debug (Software Output):').pack(
        anchor=tk.W
    )
    self.prog_monitor = tk.Text(
        prog_frame, height=4, state=tk.DISABLED, bg='#e8ecef'
    )
    prog_scroll = tk.Scrollbar(prog_frame, command=self.prog_monitor.yview)
    self.prog_monitor.configure(yscrollcommand=prog_scroll.set)
    self.prog_monitor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    prog_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    # 6. Footer Info
    footer_frame = tk.Frame(self.root)
    footer_frame.pack(fill=tk.X, padx=5, pady=(2, 4))

    tk.Label(
        footer_frame,
        text='More info: GitHub.com/JimHeaney/ESP-Config',
        font=('TkDefaultFont', 8),
        fg='gray',
    ).pack(side=tk.LEFT)

    tk.Label(
        footer_frame, text='V1.0.0', font=('TkDefaultFont', 8), fg='gray'
    ).pack(side=tk.RIGHT)

  def parse_macros(self, text, default_color='black'):
    if text is None:
      return '', default_color
    text_str = str(text)
    color = default_color

    if '[bad]' in text_str:
      color = 'red'
      text_str = text_str.replace('[bad]', '')
    elif '[good]' in text_str:
      color = 'green'
      text_str = text_str.replace('[good]', '')

    if '[time]' in text_str:
      now_str = datetime.now().strftime('%H:%M:%S')
      text_str = text_str.replace('[time]', now_str)

    return text_str, color

  def safe_int(self, val):
    if val is None or val == '':
      return None
    try:
      return int(val)
    except (ValueError, TypeError):
      return None

  def build_limit_str(self, q_type, max_len, lower_lim, upper_lim):
    limits = []
    if q_type == 'string' and max_len is not None:
      limits.append(f'Max length: {max_len}')
    elif q_type == 'integer':
      if lower_lim is not None and upper_lim is not None:
        limits.append(f'Range: {lower_lim} to {upper_lim}')
      elif lower_lim is not None:
        limits.append(f'Min: {lower_lim}')
      elif upper_lim is not None:
        limits.append(f'Max: {upper_lim}')
    return f" ({', '.join(limits)})" if limits else ''

  def request_resend(self, missing_nums):
    for num in missing_nums:
      self.log_to_prog(f'-> Requesting resend of missed payload #{num}...')
      resend_payload = {'operation': 'resend', 'message-number': num}
      self.send_payload(resend_payload)

  def set_item_unavailable_state(self, item_key, is_unavail):
    item = self.rendered_items.get(item_key)
    if not item:
      return

    item['is_unavailable'] = is_unavail
    container = item['container_frame']
    badge = item.get('unavail_badge')

    if is_unavail:
      container.config(
          bg='#f0f2f5',
          highlightbackground='#bdc3c7',
          highlightcolor='#bdc3c7',
          highlightthickness=1,
      )
      if badge:
        badge.pack(side=tk.LEFT, padx=(5, 0))

      if 'prompt_label' in item:
        item['prompt_label'].config(fg='#888888')
      if 'title_label' in item:
        item['title_label'].config(fg='#888888')

      if 'entry' in item and item['entry']:
        if isinstance(item['entry'], ttk.Combobox):
          item['entry'].config(state=tk.DISABLED)
        elif isinstance(item['entry'], tk.StringVar):
          pass
        else:
          item['entry'].config(
              state=tk.DISABLED,
              disabledbackground='#e2e8f0',
              disabledforeground='#888888',
          )
      if 'widget' in item:
        item['widget'].config(state=tk.DISABLED, disabledforeground='#888888')

      for opt_w in item.get('option_widgets', []):
        opt_w.config(state=tk.DISABLED)
    else:
      container.config(bg=self.default_container_bg, highlightthickness=0)
      if badge:
        badge.pack_forget()

      if 'prompt_label' in item:
        col = item.get('prompt_col') or 'black'
        item['prompt_label'].config(fg=col)
      if 'title_label' in item:
        col = item.get('title_col') or 'black'
        item['title_label'].config(fg=col)

      if 'entry' in item and item['entry']:
        if isinstance(item['entry'], ttk.Combobox):
          item['entry'].config(state='readonly')
        elif isinstance(item['entry'], tk.StringVar):
          pass
        else:
          item['entry'].config(state=tk.NORMAL)
      if 'widget' in item:
        item['widget'].config(state=tk.NORMAL)

      for opt_w in item.get('option_widgets', []):
        opt_w.config(state=tk.NORMAL)

  def apply_filter(self):
    query = self.search_var.get().strip().lower()

    for item_key, item in self.rendered_items.items():
      container = item.get('container_frame')
      if not container or not container.winfo_exists():
        continue

      searchable_texts = [
          str(item.get('id', '')),
          str(item.get('source', '')),
          str(item.get('category', '')),
          str(item.get('title', '')),
          str(item.get('prompt', '')),
          str(item.get('message', '')),
          str(item.get('popup', '')),
          str(item.get('original_val', '')),
          str(item.get('q_type', '')),
          ' '.join([str(o) for o in item.get('options', [])]),
      ]

      if (
          'entry' in item
          and item['entry']
          and hasattr(item['entry'], 'get')
          and not isinstance(item['entry'], tk.StringVar)
      ):
        try:
          searchable_texts.append(item['entry'].get())
        except Exception:
          pass
      if 'check_vars' in item:
        searchable_texts.extend(
            [opt for opt, var in item['check_vars'].items() if var.get()]
        )
      if 'value_label' in item and item['value_label'].winfo_exists():
        searchable_texts.append(item['value_label'].cget('text'))

      combined_text = ' '.join(searchable_texts).lower()
      match = (query in combined_text) if query else True
      item['visible_by_search'] = match

      if match:
        container.pack(fill=tk.X, pady=3)
      else:
        container.pack_forget()

    self.update_structure_visibility()

  def update_structure_visibility(self):
    visible_tab_roots = []

    for cat, tab_info in self.tabs.items():
      cat_has_visible_items = False

      for sec_type in ['information', 'commands', 'settings']:
        sec_has_visible = False
        source_dict = tab_info['source_frames'][sec_type]

        for source_name, source_frame in source_dict.items():
          has_visible_child = False
          for item in self.rendered_items.values():
            item_src = str(item.get('source', 'Core')).strip() or 'Core'
            if (
                item.get('category') == cat
                and item.get('sec_type') == sec_type
                and item_src == source_name
                and item.get('visible_by_search', True)
            ):
              has_visible_child = True
              break

          if has_visible_child:
            source_frame.pack(fill=tk.X, pady=4, expand=True)
            sec_has_visible = True
          else:
            source_frame.pack_forget()

        section = tab_info['sections'][sec_type]
        if sec_has_visible and tab_info['has_items'][sec_type]:
          section.pack(fill=tk.X, pady=4, expand=True, anchor='n')
          cat_has_visible_items = True
        else:
          section.pack_forget()

      tab_root = tab_info['tab_root']
      if cat_has_visible_items:
        try:
          self.notebook.tab(tab_root, state='normal')
        except tk.TclError:
          pass
        visible_tab_roots.append(tab_root)
      else:
        try:
          self.notebook.hide(tab_root)
        except tk.TclError:
          pass

    if visible_tab_roots:
      try:
        current_tab = self.notebook.select()
        visible_str_paths = [str(t) for t in visible_tab_roots]
        if current_tab not in visible_str_paths:
          self.notebook.select(visible_tab_roots[0])
      except tk.TclError:
        self.notebook.select(visible_tab_roots[0])

  def toggle_config_visibility(self):
    self.show_config_messages = self.show_config_var.get()
    self.hide_ack_messages = self.hide_ack_var.get()

    if self.show_config_messages:
      self.hide_ack_chk.config(state=tk.NORMAL)
    else:
      self.hide_ack_chk.config(state=tk.DISABLED)

  def refresh_ports(self):
    ports = [port.device for port in serial.tools.list_ports.comports()]
    self.port_cb['values'] = ports
    if ports:
      self.port_cb.current(0)

  def log_to_monitor(self, text):
    self.monitor.config(state=tk.NORMAL)
    self.monitor.insert(tk.END, text + '\n', 'hanging_indent')
    self.monitor.see(tk.END)
    self.monitor.config(state=tk.DISABLED)

  def log_to_prog(self, text):
    self.prog_monitor.config(state=tk.NORMAL)
    self.prog_monitor.insert(tk.END, text + '\n')
    self.prog_monitor.see(tk.END)
    self.prog_monitor.config(state=tk.DISABLED)

  def set_password(self):
    self.current_password = self.pass_entry.get()
    self.pass_status.config(text='Status: Sending...', fg='orange')
    self.log_to_prog(
        '-> Password updated. Transmitting password payload immediately...'
    )
    self.send_payload({})

  def calculate_hash(self, payload_dict):
    payload_copy = json.loads(json.dumps(payload_dict))
    if 'metadata' in payload_copy:
      payload_copy['metadata']['hash'] = '0'
    json_bytes = json.dumps(payload_copy, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(json_bytes).hexdigest()

  def create_metadata(self):
    meta = {
        'hash': '0',
        'version': 1,
        'message-number': self.tx_message_number,
    }
    if self.current_password:
      meta['password'] = self.current_password
    self.tx_message_number += 1
    return meta

  def send_payload(self, payload_dict):
    if not (
        self.is_connected and self.serial_port and self.serial_port.is_open
    ):
      self.log_to_prog('Error: Cannot send payload (Not connected).')
      return

    payload_dict['metadata'] = self.create_metadata()
    payload_dict['metadata']['hash'] = self.calculate_hash(payload_dict)

    json_msg = json.dumps(payload_dict) + '\n'
    try:
      self.serial_port.write(json_msg.encode('utf-8'))
      self.log_to_prog(f'-> Sent: {json_msg.strip()}')
      if self.current_password:
        self.pass_status.config(text='Status: Sent', fg='blue')
    except Exception as e:
      self.log_to_prog(f'Error sending payload: {e}')

  def send_answers(self, category):
    answers = []
    for item_key, item in self.rendered_items.items():
      if item.get('type') == 'question' and item.get('category') == category:
        if item.get('is_unavailable'):
          continue

        item_id = item.get('id')
        q_type = item.get('q_type', 'string')
        max_len = item.get('max_length')
        upper_lim = item.get('upper_limit')
        lower_lim = item.get('lower_limit')
        options = item.get('options', [])

        if q_type == 'selection':
          check_vars = item.get('check_vars', {})
          val = [opt for opt, var in check_vars.items() if var.get()]

        elif q_type == 'choice':
          val = item['entry'].get()
          if options and val not in options:
            msg = f"Selection for '{item_id}' ({val}) is not a valid option."
            messagebox.showwarning('Invalid Choice', msg)
            self.log_to_prog(f'Error: {msg}')
            return

        elif q_type == 'integer':
          raw_val = item['entry'].get()
          try:
            val = int(raw_val)
          except ValueError:
            msg = f"Value for '{item_id}' must be a valid integer."
            messagebox.showwarning('Validation Error', msg)
            self.log_to_prog(f'Error: {msg}')
            return

          if lower_lim is not None and val < lower_lim:
            msg = (
                f"Value for '{item_id}' ({val}) is below minimum limit"
                f' ({lower_lim}).'
            )
            messagebox.showwarning('Out of Bounds', msg)
            self.log_to_prog(f'Error: {msg}')
            return

          if upper_lim is not None and val > upper_lim:
            msg = (
                f"Value for '{item_id}' ({val}) exceeds maximum limit"
                f' ({upper_lim}).'
            )
            messagebox.showwarning('Out of Bounds', msg)
            self.log_to_prog(f'Error: {msg}')
            return

        elif q_type == 'string':
          val = item['entry'].get()
          if max_len is not None and len(val) > max_len:
            msg = (
                f"Value for '{item_id}' length ({len(val)}) exceeds max length"
                f' ({max_len}).'
            )
            messagebox.showwarning('Out of Bounds', msg)
            self.log_to_prog(f'Error: {msg}')
            return
        else:
          val = item['entry'].get()

        ans_obj = {'id': item_id, 'answer': val}
        if item.get('source'):
          ans_obj['source'] = item['source']

        answers.append(ans_obj)
        item['original_val'] = val

    if answers:
      payload = {'answers': answers}
      self.send_payload(payload)
    else:
      self.log_to_prog(f"No answers found to send for category '{category}'.")

  def discard_answers(self, category):
    count = 0
    for item_key, item in self.rendered_items.items():
      if item.get('type') == 'question' and item.get('category') == category:
        if not item.get('is_unavailable'):
          q_type = item.get('q_type')
          orig = item.get('original_val')

          if q_type == 'selection':
            orig_list = (
                orig if isinstance(orig, list) else ([orig] if orig else [])
            )
            for opt, var in item.get('check_vars', {}).items():
              var.set(opt in orig_list)
          elif q_type == 'choice':
            item['entry'].set(orig)
          else:
            item['entry'].delete(0, tk.END)
            item['entry'].insert(0, str(orig))
          count += 1
    self.log_to_prog(
        f"Discarded changes for {count} answer(s) in category '{category}'."
    )

  def send_command(self, item_key, input_val):
    item = self.rendered_items.get(item_key, {})
    if item.get('is_unavailable'):
      return

    item_id = item.get(
        'id', item_key[1] if isinstance(item_key, tuple) else item_key
    )
    max_len = item.get('max_length')

    if isinstance(input_val, str) and max_len is not None:
      if len(input_val) > max_len:
        msg = (
            f'Command input length ({len(input_val)}) exceeds max length'
            f' ({max_len}).'
        )
        messagebox.showwarning('Out of Bounds', msg)
        self.log_to_prog(f'Error: {msg}')
        return

    cmd_obj = {'id': item_id, 'input': input_val}
    if item.get('source'):
      cmd_obj['source'] = item['source']

    payload = {'commands': [cmd_obj]}
    self.send_payload(payload)

  def toggle_connection(self):
    if self.is_connected:
      self.disconnect()
    else:
      self.connect()

  def connect(self):
    port = self.port_cb.get()
    if not port:
      return
    try:
      self.serial_port = serial.Serial(port, 115200, timeout=1)
      self.is_connected = True
      self.tx_message_number = 0
      self.last_rx_message_num = 0
      self.received_msg_numbers.clear()
      self.highest_contiguous_rx = 0

      self.connect_btn.config(text='Disconnect')
      self.log_to_prog(f'--- Connected to {port} ---')

      self.read_thread = threading.Thread(
          target=self.read_from_port, daemon=True
      )
      self.read_thread.start()

      start_payload = json.dumps({'operation': 'start'}) + '\n'
      self.serial_port.write(start_payload.encode('utf-8'))

      self.root.after(1000, self.send_keep_alive)

    except Exception as e:
      self.log_to_prog(f'Error connecting: {e}')

  def send_keep_alive(self):
    if self.is_connected and self.serial_port and self.serial_port.is_open:
      try:
        check_payload = (
            json.dumps({
                'operation': 'check',
                'last': self.highest_contiguous_rx,
            })
            + '\n'
        )
        self.serial_port.write(check_payload.encode('utf-8'))
      except Exception as e:
        self.log_to_prog(f'Error sending keep-alive: {e}')

      self.root.after(1000, self.send_keep_alive)

  def disconnect(self):
    self.is_connected = False
    if self.serial_port and self.serial_port.is_open:
      end_payload = json.dumps({'operation': 'end'}) + '\n'
      self.serial_port.write(end_payload.encode('utf-8'))
      self.serial_port.close()

    self.connect_btn.config(text='Connect')
    self.log_to_prog('--- Disconnected ---')

    self.current_password = ''
    self.pass_entry.delete(0, tk.END)
    self.pass_status.config(text='Status: Not Set', fg='gray')
    self.pass_hint.config(text='Hint: (Waiting for device...)', fg='blue')
    if not self.pass_frame.winfo_ismapped():
      self.pass_frame.pack(pady=5, padx=5, fill=tk.X, before=self.notebook)

    self.received_msg_numbers.clear()
    self.highest_contiguous_rx = 0
    self.last_rx_message_num = 0

    for tab_dict in self.tabs.values():
      tab_dict['tab_root'].destroy()
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
              .decode('utf-8', errors='ignore')
              .strip()
          )
          if not line:
            continue

          if line.startswith('[config]'):
            json_start = line.find('{')
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
                  payload.get('operation') == 'ack'
                  or payload.get('type') == 'ack'
                  or 'ack' in payload
              ):
                is_ack = True
            elif 'ack' in line.lower():
              is_ack = True

            if self.show_config_messages:
              if not (self.hide_ack_messages and is_ack):
                self.root.after(0, self.log_to_monitor, line)

            if json_start != -1:
              if payload is not None:
                self.root.after(0, self.update_gui_with_payload, payload)
              else:
                self.root.after(
                    0,
                    self.log_to_prog,
                    'Error: Received malformed JSON configuration.',
                )
            else:
              self.root.after(
                  0,
                  self.log_to_prog,
                  'Error: Missing JSON body in config payload.',
              )
          else:
            self.root.after(0, self.log_to_monitor, line)
      except Exception as e:
        if self.is_connected:
          self.root.after(0, self.log_to_prog, f'Serial read error: {e}')
        break

  def ensure_category_tab(self, category):
    if category in self.tabs:
      return

    tab_root = tk.Frame(self.notebook)
    self.notebook.add(tab_root, text=category)

    canvas = tk.Canvas(tab_root, highlightthickness=0)
    scrollbar = tk.Scrollbar(tab_root, orient='vertical', command=canvas.yview)
    scrollable_frame = tk.Frame(canvas)

    scrollable_frame.bind(
        '<Configure>',
        lambda e: canvas.configure(scrollregion=canvas.bbox('all')),
    )

    canvas_window = canvas.create_window(
        (0, 0), window=scrollable_frame, anchor='nw'
    )

    canvas.bind(
        '<Configure>', lambda e: canvas.itemconfig(canvas_window, width=e.width)
    )

    def _on_mousewheel(event):
      if event.num == 4:
        canvas.yview_scroll(-1, 'units')
      elif event.num == 5:
        canvas.yview_scroll(1, 'units')
      elif event.delta:
        canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')

    def _bind_mousewheel(event):
      canvas.bind_all('<MouseWheel>', _on_mousewheel)
      canvas.bind_all('<Button-4>', _on_mousewheel)
      canvas.bind_all('<Button-5>', _on_mousewheel)

    def _unbind_mousewheel(event):
      canvas.unbind_all('<MouseWheel>')
      canvas.unbind_all('<Button-4>')
      canvas.unbind_all('<Button-5>')

    canvas.bind('<Enter>', _bind_mousewheel)
    canvas.bind('<Leave>', _unbind_mousewheel)

    scrollbar.pack(side='right', fill='y')
    canvas.pack(side='left', fill='both', expand=True)

    info_sec = CollapsibleSection(scrollable_frame, title='Information')
    cmd_sec = CollapsibleSection(scrollable_frame, title='Commands')
    settings_sec = CollapsibleSection(scrollable_frame, title='Settings')

    send_answers_btn = tk.Button(
        settings_sec.header_extras,
        text='Send Answers',
        command=lambda cat=category: self.send_answers(cat),
    )
    send_answers_btn.pack(side=tk.LEFT, padx=2)

    discard_answers_btn = tk.Button(
        settings_sec.header_extras,
        text='Discard Answers',
        command=lambda cat=category: self.discard_answers(cat),
    )
    discard_answers_btn.pack(side=tk.LEFT, padx=2)

    info_sec.pack_forget()
    cmd_sec.pack_forget()
    settings_sec.pack_forget()

    self.tabs[category] = {
        'tab_root': tab_root,
        'sections': {
            'information': info_sec,
            'commands': cmd_sec,
            'settings': settings_sec,
        },
        'source_frames': {
            'information': {},
            'commands': {},
            'settings': {},
        },
        'has_items': {
            'information': False,
            'commands': False,
            'settings': False,
        },
    }

  def get_source_frame(self, category, sec_type, source):
    source_name = (
        str(source).strip() if source and str(source).strip() else 'Core'
    )
    section_frame = self.tabs[category]['sections'][sec_type].content_frame
    source_dict = self.tabs[category]['source_frames'][sec_type]

    if source_name not in source_dict:
      lf = tk.LabelFrame(
          section_frame,
          text=f' {source_name} ',
          font=('TkDefaultFont', 8, 'bold'),
          fg='#333333',
          padx=5,
          pady=5,
      )
      lf.pack(fill=tk.X, pady=4, expand=True)
      source_dict[source_name] = lf

    return source_dict[source_name]

  def show_section(self, category, sec_type):
    tab_info = self.tabs[category]
    if not tab_info['has_items'][sec_type]:
      tab_info['has_items'][sec_type] = True
      for key in ['information', 'commands', 'settings']:
        if tab_info['has_items'][key]:
          tab_info['sections'][key].pack(
              fill=tk.X, pady=4, expand=True, anchor='n'
          )

  def update_gui_with_payload(self, payload):
    # 1. Sequence & Metadata Tracking
    if 'metadata' in payload:
      meta = payload['metadata']

      if 'message-number' in meta:
        rx_num = meta['message-number']

        if rx_num not in self.received_msg_numbers:
          self.received_msg_numbers.add(rx_num)

          # Gap detection logic
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
                  f'⚠️ Sequence gap! Expected {self.last_rx_message_num + 1},'
                  f' received {rx_num}. Missing: {missing}'
              )
              self.request_resend(missing)

          # Update highest contiguous RX number
          while (
              self.highest_contiguous_rx + 1
          ) in self.received_msg_numbers:
            self.highest_contiguous_rx += 1

          if rx_num > self.last_rx_message_num:
            self.last_rx_message_num = rx_num

      if 'hint' in meta:
        hint_clean, hint_col = self.parse_macros(
            f"Hint: {meta['hint']}", default_color='blue'
        )
        self.pass_hint.config(text=hint_clean, fg=hint_col)

      if 'password-correct' in meta:
        if meta['password-correct']:
          self.pass_status.config(text='Status: Correct', fg='green')
          self.pass_frame.pack_forget()
        else:
          if not self.pass_frame.winfo_ismapped():
            self.pass_frame.pack(
                pady=5, padx=5, fill=tk.X, before=self.notebook
            )
          self.pass_status.config(text='Status: Incorrect', fg='red')

    # 2. Render Information items
    if 'information' in payload:
      for info in payload['information']:
        item_id = info.get('id')
        source = info.get('source', 'Core')
        item_key = (source, item_id)
        raw_cat = info.get('category')

        if item_key in self.rendered_items:
          if 'value' in info:
            val_clean, val_col = self.parse_macros(
                info.get('value', ''), default_color='black'
            )
            self.rendered_items[item_key]['value_label'].config(
                text=val_clean, fg=val_col
            )
          continue

        if not raw_cat or not str(raw_cat).strip():
          self.log_to_prog(
              f"Ignored info item '{item_id}' from source '{source}':"
              ' Unrecognized item and missing category.'
          )
          continue

        category = str(raw_cat).strip()
        self.ensure_category_tab(category)
        self.show_section(category, 'information')

        target_frame = self.get_source_frame(category, 'information', source)
        container = tk.Frame(target_frame)
        container.pack(fill=tk.X, pady=3)

        row_frame = tk.Frame(container)
        row_frame.pack(fill=tk.X)

        title_clean, title_col = self.parse_macros(
            info.get('title', 'Info'), default_color='black'
        )
        title_label = tk.Label(
            row_frame,
            text=f'{title_clean}: ',
            font=('TkDefaultFont', 9, 'bold'),
            fg=title_col,
        )
        title_label.pack(side=tk.LEFT)

        val_clean, val_col = self.parse_macros(
            info.get('value', ''), default_color='black'
        )
        value_label = tk.Label(row_frame, text=val_clean, fg=val_col)
        value_label.pack(side=tk.LEFT)

        popup_raw = info.get('pop-up', '') or info.get('explanation', '')
        popup_text, _ = self.parse_macros(popup_raw)
        if popup_text:
          help_label = tk.Label(
              row_frame, text=' ❓ ', fg='blue', cursor='question_arrow'
          )
          help_label.pack(side=tk.LEFT)
          help_label.tooltip = ToolTip(help_label, popup_text)

        self.rendered_items[item_key] = {
            'id': item_id,
            'type': 'info',
            'sec_type': 'information',
            'source': source,
            'category': category,
            'title': title_clean,
            'container_frame': container,
            'row_frame': row_frame,
            'title_label': title_label,
            'title_col': title_col,
            'value_label': value_label,
            'popup': popup_text,
            'visible_by_search': True,
        }

    # 3. Render Questions (Settings)
    if 'questions' in payload:
      for q in payload['questions']:
        item_id = q.get('id')
        source = q.get('source', 'Core')
        item_key = (source, item_id)
        raw_cat = q.get('category')

        if item_key in self.rendered_items:
          item_ref = self.rendered_items[item_key]

          # --- Dynamic Options Update ---
          if 'options' in q and q['options'] != item_ref.get('options'):
            new_opts = q['options']
            item_ref['options'] = new_opts
            q_type = item_ref.get('q_type')

            if (
                q_type == 'choice'
                and isinstance(item_ref.get('entry'), ttk.Combobox)
                and len(new_opts) > 4
            ):
              item_ref['entry']['values'] = new_opts
            else:
              for opt_w in item_ref.get('option_widgets', []):
                opt_w.destroy()
              item_ref['option_widgets'] = []

              if (
                  'opt_frame' in item_ref
                  and item_ref['opt_frame']
                  and item_ref['opt_frame'].winfo_exists()
              ):
                item_ref['opt_frame'].destroy()
                item_ref['opt_frame'] = None

              if isinstance(item_ref.get('entry'), ttk.Combobox):
                item_ref['entry'].destroy()
                item_ref['entry'] = None

              row_frame = item_ref['row_frame']
              current_val = q.get('current', item_ref.get('original_val', ''))

              if q_type == 'selection':
                curr_list = (
                    current_val
                    if isinstance(current_val, list)
                    else ([current_val] if current_val else [])
                )
                item_ref['check_vars'] = {}

                opt_frame = tk.Frame(row_frame)
                opt_frame.pack(side=tk.LEFT, padx=5)
                item_ref['opt_frame'] = opt_frame

                for opt in new_opts:
                  var = tk.BooleanVar(value=(opt in curr_list))
                  cb = tk.Checkbutton(opt_frame, text=opt, variable=var)
                  cb.pack(side=tk.LEFT, padx=4)
                  item_ref['check_vars'][opt] = var
                  item_ref['option_widgets'].append(cb)

              elif q_type == 'choice':
                if len(new_opts) <= 4 and new_opts:
                  opt_frame = tk.Frame(row_frame)
                  opt_frame.pack(side=tk.LEFT, padx=5)
                  item_ref['opt_frame'] = opt_frame
                  radio_var = tk.StringVar(value=str(current_val))

                  for opt in new_opts:
                    rb = tk.Radiobutton(
                        opt_frame,
                        text=opt,
                        value=opt,
                        variable=radio_var,
                        tristatevalue='',
                    )
                    rb.pack(side=tk.LEFT, padx=4)
                    item_ref['option_widgets'].append(rb)
                  item_ref['entry'] = radio_var
                else:
                  entry_widget = ttk.Combobox(
                      row_frame, values=new_opts, state='readonly'
                  )
                  str_curr = str(current_val)
                  if str_curr in new_opts:
                    entry_widget.set(str_curr)
                  elif new_opts:
                    entry_widget.current(0)
                  else:
                    entry_widget.set(str_curr)
                  entry_widget.pack(
                      side=tk.LEFT, padx=5, fill=tk.X, expand=True
                  )
                  item_ref['entry'] = entry_widget

          if 'message' in q:
            msg_clean, msg_col = self.parse_macros(
                q.get('message', ''), default_color='#555555'
            )
            item_ref['msg_label'].config(text=msg_clean, fg=msg_col)
            item_ref['message'] = msg_clean

          if 'current' in q:
            new_curr = q.get('current', '')
            item_ref['original_val'] = new_curr
            if item_ref.get('q_type') == 'selection':
              curr_list = (
                  new_curr
                  if isinstance(new_curr, list)
                  else ([new_curr] if new_curr else [])
              )
              for opt, var in item_ref.get('check_vars', {}).items():
                var.set(opt in curr_list)
            elif item_ref.get('q_type') == 'choice':
              if isinstance(item_ref.get('entry'), ttk.Combobox):
                item_ref['entry'].set(str(new_curr))
              elif isinstance(item_ref.get('entry'), tk.StringVar):
                item_ref['entry'].set(str(new_curr))
            else:
              item_ref['entry'].delete(0, tk.END)
              item_ref['entry'].insert(0, str(new_curr))

          if 'unavailable' in q:
            is_unavail = bool(q.get('unavailable'))
            self.set_item_unavailable_state(item_key, is_unavail)
          continue

        if not raw_cat or not str(raw_cat).strip():
          self.log_to_prog(
              f"Ignored question item '{item_id}' from source '{source}':"
              ' Unrecognized item and missing category.'
          )
          continue

        category = str(raw_cat).strip()
        q_type = q.get('type', 'string')
        max_len = self.safe_int(q.get('max-length'))
        lower_lim = self.safe_int(q.get('lower-limit'))
        upper_lim = self.safe_int(q.get('upper-limit'))
        options = (
            q.get('options', []) if q_type in ['choice', 'selection'] else []
        )
        is_unavail = bool(q.get('unavailable', False))

        self.ensure_category_tab(category)
        self.show_section(category, 'settings')

        target_frame = self.get_source_frame(category, 'settings', source)
        q_container = tk.Frame(target_frame)
        q_container.pack(fill=tk.X, pady=3)

        row_frame = tk.Frame(q_container)
        row_frame.pack(fill=tk.X)

        limit_str = self.build_limit_str(q_type, max_len, lower_lim, upper_lim)
        prompt_clean, prompt_col = self.parse_macros(
            q.get('prompt', 'Question:'), default_color='black'
        )
        prompt_text = f'{prompt_clean}{limit_str}'

        prompt_label = tk.Label(row_frame, text=prompt_text, fg=prompt_col)
        prompt_label.pack(side=tk.LEFT)

        unavail_badge = tk.Label(
            row_frame,
            text=' 🚫 UNAVAILABLE ',
            bg='#6c757d',
            fg='white',
            font=('TkDefaultFont', 7, 'bold'),
            padx=3,
            pady=1,
        )

        current_val = q.get('current', '')
        option_widgets = []
        check_vars = {}
        entry_widget = None
        opt_frame = None

        if q_type == 'selection':
          curr_list = (
              current_val
              if isinstance(current_val, list)
              else ([current_val] if current_val else [])
          )
          opt_frame = tk.Frame(row_frame)
          opt_frame.pack(side=tk.LEFT, padx=5)

          for opt in options:
            var = tk.BooleanVar(value=(opt in curr_list))
            cb = tk.Checkbutton(opt_frame, text=opt, variable=var)
            cb.pack(side=tk.LEFT, padx=4)
            check_vars[opt] = var
            option_widgets.append(cb)

        elif q_type == 'choice':
          if len(options) <= 4 and options:
            opt_frame = tk.Frame(row_frame)
            opt_frame.pack(side=tk.LEFT, padx=5)
            radio_var = tk.StringVar(value=str(current_val))

            for opt in options:
              rb = tk.Radiobutton(
                  opt_frame,
                  text=opt,
                  value=opt,
                  variable=radio_var,
                  tristatevalue='',
              )
              rb.pack(side=tk.LEFT, padx=4)
              option_widgets.append(rb)
            entry_widget = radio_var
          else:
            entry_widget = ttk.Combobox(
                row_frame, values=options, state='readonly'
            )
            str_curr = str(current_val)
            if str_curr in options:
              entry_widget.set(str_curr)
            elif options:
              entry_widget.current(0)
            else:
              entry_widget.set(str_curr)
            entry_widget.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        else:
          entry_widget = tk.Entry(row_frame)
          entry_widget.insert(0, str(current_val))
          entry_widget.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        msg_clean, msg_col = self.parse_macros(
            q.get('message', ''), default_color='#555555'
        )
        msg_label = tk.Label(
            q_container,
            text=msg_clean,
            fg=msg_col,
            anchor='w',
            justify=tk.LEFT,
            font=('TkDefaultFont', 8, 'italic'),
        )
        msg_label.pack(fill=tk.X, padx=(10, 0))

        self.rendered_items[item_key] = {
            'id': item_id,
            'type': 'question',
            'sec_type': 'settings',
            'q_type': q_type,
            'options': options,
            'source': source,
            'category': category,
            'prompt': prompt_clean,
            'message': msg_clean,
            'max_length': max_len,
            'upper_limit': upper_lim,
            'lower_limit': lower_lim,
            'container_frame': q_container,
            'row_frame': row_frame,
            'opt_frame': opt_frame,
            'msg_label': msg_label,
            'prompt_label': prompt_label,
            'prompt_col': prompt_col,
            'entry': entry_widget,
            'check_vars': check_vars,
            'option_widgets': option_widgets,
            'original_val': current_val,
            'unavail_badge': unavail_badge,
            'is_unavailable': is_unavail,
            'visible_by_search': True,
        }

        self.set_item_unavailable_state(item_key, is_unavail)

    # 4. Render Commands
    if 'commands' in payload:
      for cmd in payload['commands']:
        item_id = cmd.get('id')
        source = cmd.get('source', 'Core')
        item_key = (source, item_id)
        raw_cat = cmd.get('category')

        if item_key in self.rendered_items:
          item_ref = self.rendered_items[item_key]
          if 'message' in cmd and 'msg_label' in item_ref:
            msg_clean, msg_col = self.parse_macros(
                cmd.get('message', ''), default_color='#555555'
            )
            item_ref['msg_label'].config(text=msg_clean, fg=msg_col)
            item_ref['message'] = msg_clean
          if 'pop-up' in cmd:
            popup_clean, _ = self.parse_macros(cmd.get('pop-up'))
            item_ref['popup'] = popup_clean
          if 'unavailable' in cmd:
            is_unavail = bool(cmd.get('unavailable'))
            self.set_item_unavailable_state(item_key, is_unavail)
          continue

        if not raw_cat or not str(raw_cat).strip():
          self.log_to_prog(
              f"Ignored command item '{item_id}' from source '{source}':"
              ' Unrecognized item and missing category.'
          )
          continue

        category = str(raw_cat).strip()
        cmd_type = cmd.get('type', 'button')
        popup_clean, _ = self.parse_macros(cmd.get('pop-up'))
        msg_clean, msg_col = self.parse_macros(
            cmd.get('message', ''), default_color='#555555'
        )
        max_len = self.safe_int(cmd.get('max-length'))
        is_unavail = bool(cmd.get('unavailable', False))

        self.ensure_category_tab(category)
        self.show_section(category, 'commands')

        target_frame = self.get_source_frame(category, 'commands', source)
        cmd_container = tk.Frame(target_frame)
        cmd_container.pack(fill=tk.X, pady=3)

        row_frame = tk.Frame(cmd_container)
        row_frame.pack(fill=tk.X)

        unavail_badge = tk.Label(
            row_frame,
            text=' 🚫 UNAVAILABLE ',
            bg='#6c757d',
            fg='white',
            font=('TkDefaultFont', 7, 'bold'),
            padx=3,
            pady=1,
        )

        if cmd_type in ['string', 'text', 'input']:
          title_raw = cmd.get('title', cmd.get('prompt', 'Command:'))
          title_clean, title_col = self.parse_macros(
              title_raw, default_color='black'
          )
          if max_len is not None:
            title_clean += f' (Max length: {max_len})'

          label = tk.Label(row_frame, text=title_clean + ' ', fg=title_col)
          label.pack(side=tk.LEFT)

          cmd_entry = tk.Entry(row_frame)
          cmd_entry.insert(0, str(cmd.get('current', '')))
          cmd_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

          def on_send_string(c_key=item_key, entry_widget=cmd_entry):
            p_text = self.rendered_items[c_key].get('popup')
            if p_text and not messagebox.askokcancel('Confirm Command', p_text):
              return
            self.send_command(c_key, entry_widget.get())

          send_btn = tk.Button(
              row_frame,
              text='➔',
              fg='green',
              font=('TkDefaultFont', 9, 'bold'),
              command=on_send_string,
          )
          send_btn.pack(side=tk.LEFT, padx=2)

          msg_label = tk.Label(
              cmd_container,
              text=msg_clean,
              fg=msg_col,
              anchor='w',
              justify=tk.LEFT,
              font=('TkDefaultFont', 8, 'italic'),
          )
          msg_label.pack(fill=tk.X, padx=(10, 0))

          self.rendered_items[item_key] = {
              'id': item_id,
              'type': 'command',
              'sec_type': 'commands',
              'source': source,
              'category': category,
              'title': title_clean,
              'message': msg_clean,
              'max_length': max_len,
              'container_frame': cmd_container,
              'row_frame': row_frame,
              'title_label': label,
              'title_col': title_col,
              'widget': send_btn,
              'entry': cmd_entry,
              'popup': popup_clean,
              'msg_label': msg_label,
              'unavail_badge': unavail_badge,
              'is_unavailable': is_unavail,
              'visible_by_search': True,
          }

        elif cmd_type == 'latch':
          title_clean, title_col = self.parse_macros(
              cmd.get('title', 'Command'), default_color='black'
          )
          btn = tk.Button(row_frame, text=title_clean, fg=title_col)
          btn.pack(side=tk.LEFT)

          initial_latched = bool(cmd.get('current', False))
          if initial_latched:
            btn.config(relief=tk.SUNKEN, bg='#a0d0a0')

          def toggle_latch(c_key=item_key, b=btn):
            item_ref = self.rendered_items[c_key]
            if item_ref.get('is_unavailable'):
              return
            p_text = item_ref.get('popup')
            if p_text and not messagebox.askokcancel('Confirm Command', p_text):
              return

            new_state = not item_ref.get('is_latched', False)
            item_ref['is_latched'] = new_state

            if new_state:
              b.config(relief=tk.SUNKEN, bg='#a0d0a0')
            else:
              b.config(relief=tk.RAISED, bg=self.default_btn_bg)

            self.send_command(c_key, new_state)

          btn.config(command=toggle_latch)

          msg_label = tk.Label(
              cmd_container,
              text=msg_clean,
              fg=msg_col,
              anchor='w',
              justify=tk.LEFT,
              font=('TkDefaultFont', 8, 'italic'),
          )
          msg_label.pack(fill=tk.X, padx=(10, 0))

          self.rendered_items[item_key] = {
              'id': item_id,
              'type': 'command',
              'sec_type': 'commands',
              'source': source,
              'category': category,
              'title': title_clean,
              'message': msg_clean,
              'container_frame': cmd_container,
              'row_frame': row_frame,
              'title_label': btn,
              'title_col': title_col,
              'widget': btn,
              'popup': popup_clean,
              'is_latched': initial_latched,
              'msg_label': msg_label,
              'unavail_badge': unavail_badge,
              'is_unavailable': is_unavail,
              'visible_by_search': True,
          }

        else:
          title_clean, title_col = self.parse_macros(
              cmd.get('title', 'Command'), default_color='black'
          )
          btn = tk.Button(row_frame, text=title_clean, fg=title_col)
          btn.pack(side=tk.LEFT)

          def handle_popup_btn(c_key=item_key, b=btn):
            p_text = self.rendered_items[c_key].get('popup')
            confirmed = (
                messagebox.askokcancel('Confirm Command', p_text)
                if p_text
                else True
            )
            cmd_state = (
                tk.DISABLED
                if self.rendered_items[c_key].get('is_unavailable')
                else tk.NORMAL
            )
            b.config(state=cmd_state)
            if confirmed:
              self.send_command(c_key, True)
              self.send_command(c_key, False)

          def on_press(e, c_key=item_key, b=btn):
            if self.rendered_items[c_key].get('is_unavailable'):
              return
            p_text = self.rendered_items[c_key].get('popup')
            if p_text:
              self.root.after(10, lambda: handle_popup_btn(c_key, b))
            else:
              self.send_command(c_key, True)

          def on_release(e, c_key=item_key, b=btn):
            if self.rendered_items[c_key].get('is_unavailable'):
              return
            p_text = self.rendered_items[c_key].get('popup')
            if not p_text:
              self.send_command(c_key, False)
              cmd_state = (
                  tk.DISABLED
                  if self.rendered_items[c_key].get('is_unavailable')
                  else tk.NORMAL
              )
              b.config(relief=tk.RAISED, state=cmd_state)

          btn.bind('<ButtonPress-1>', on_press)
          btn.bind('<ButtonRelease-1>', on_release)

          msg_label = tk.Label(
              cmd_container,
              text=msg_clean,
              fg=msg_col,
              anchor='w',
              justify=tk.LEFT,
              font=('TkDefaultFont', 8, 'italic'),
          )
          msg_label.pack(fill=tk.X, padx=(10, 0))

          self.rendered_items[item_key] = {
              'id': item_id,
              'type': 'command',
              'sec_type': 'commands',
              'source': source,
              'category': category,
              'title': title_clean,
              'message': msg_clean,
              'container_frame': cmd_container,
              'row_frame': row_frame,
              'title_label': btn,
              'title_col': title_col,
              'widget': btn,
              'popup': popup_clean,
              'msg_label': msg_label,
              'unavail_badge': unavail_badge,
              'is_unavailable': is_unavail,
              'visible_by_search': True,
          }

        self.set_item_unavailable_state(item_key, is_unavail)

    if self.search_var.get().strip():
      self.apply_filter()


if __name__ == '__main__':
  root = tk.Tk()
  root.geometry('1000x1000')
  app = ESPConfigApp(root)
  root.mainloop()