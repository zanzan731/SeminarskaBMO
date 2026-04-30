import os, bluetooth,re, subprocess, time, curses, signal, threading
import logging
log = logging.getLogger(__name__)
from pydbus import SystemBus

# Vendor OUI Dictionary for Identification
VENDORS = {
    "34:AB:37": "Apple/iPhone?", "AC:3C:0B": "Apple/iPhone?", "F0:D1:A9": "Apple/iPhone?",
    "00:1A:7D": "CSR Dongle?", "BC:D1:D3": "Samsung?", "94:8B:C1": "Samsung?",
    "D8:6C:63": "Google/Pixel?", "CC:F9:E8": "Xiaomi?", "8C:85:90": "Huawei?",
}

def get_vendor(mac):
    prefix = mac.upper()[:8]
    return VENDORS.get(prefix, "Unknown Device")

def get_adapter_path(bus):
    """Dynamically resolve the adapter path to avoid KeyErrors."""
    try:
        mngr = bus.get("org.bluez", "/")
        objs = mngr.GetManagedObjects()
        for path, interfaces in objs.items():
            if "org.bluez.Adapter1" in interfaces:
                return path
    except: pass
    return "/org/bluez/hci0" # Default fallback

def resolve_name(addr):
    """Try to resolve device name using hcitool as a backup."""
    try:
        result = subprocess.run(["hcitool", "name", addr], capture_output=True, text=True, timeout=2)
        name = result.stdout.strip()
        return name if name else None
    except:
        return None

def get_services(addr):
    """Retrieve UUID/Services and RSSI using native DBus (Most Reliable)."""
    print(f"\n[!] Performing Discovery for {addr}...")
    
    try:
        bus = SystemBus()
        adapter_path = get_adapter_path(bus)
        print(f"Using adapter: {adapter_path}")
        adapter = bus.get("org.bluez", adapter_path)
        adapter.StartDiscovery()
        time.sleep(3) 
        
        device_path = f"{adapter_path}/dev_{addr.replace(':', '_')}"
        device = bus.get("org.bluez", device_path)
        
        # Extract properties
        uuids = getattr(device, "UUIDs", [])
        if uuids:
            print("\n--- Services & UUIDs (Native DBus) ---")
            for u in uuids:
                print(f"-> {u}")
        
        rssi = getattr(device, "RSSI", None)
        if rssi is not None:
            print(f"[+] Current RSSI: {rssi} dBm")
        else:
            print("[!] RSSI not yet available. Device might be hidden or out of range.")
                
    except Exception as e:
        print(f"Discovery error: {e}")
        print("[?] Tip: Make sure the device is in discoverable/pairing mode.")
    finally:
        if adapter:
            try: adapter.StopDiscovery()
            except: pass

def track_rssi(addr):
    """Real-time RSSI tracking using native DBus StartDiscovery pulse."""
    """Monitor real-time RSSI for a single device using native DBus."""
    print(f"\n[!] Tracking RSSI for {addr} (Ctrl+C to stop)...")
    try:
        bus = SystemBus()
        adapter_path = get_adapter_path(bus)
        adapter = bus.get("org.bluez", adapter_path)
        adapter.StartDiscovery()
        
        device_path = f"{adapter_path}/dev_{addr.replace(':', '_')}"
        try:
            device = bus.get("org.bluez", device_path)
        except:
            print(f"[!] Target {addr} not initialized in DBus. Try scanning again.")
            return

        while True:
            try:
                # Direct property access (kept live by StartDiscovery)
                rssi_val = device.RSSI
                bar_len = max(0, min(50, (rssi_val + 110) // 2))
                bar = "█" * bar_len + "-" * (50 - bar_len)
                print(f"\rRSSI: {rssi_val} dBm |{bar}|", end="", flush=True)
            except AttributeError:
                print(f"\r[!] {addr} Searching... (Waiting for DBus property)    ", end="", flush=True)
            except Exception:
                pass
            
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n[!] Radar stopped.")
    except Exception as e:
        print(f"\nRadar Error: {e}")
    finally:
        if adapter:
            try: adapter.StopDiscovery()
            except: pass

def track_all_named_rssi():
    """Display real-time RSSI dashboard for all named devices in range."""
    print(f"\n[!] Starting Global Proximity Dashboard (Named Devices Only)")
    print("[!] Pulse-monitoring all DBus device properties...")
    print("[!] Press Ctrl+C to stop.")
    
    adapter = None
    try:
        bus = SystemBus()
        adapter_path = get_adapter_path(bus)
        adapter = bus.get("org.bluez", adapter_path)
        adapter.StartDiscovery()
        
        while True:
            # Clear screen for a dashboard feel
            os.system('clear')
            print("=== BlueDucky Global Proximity Dashboard (Ctrl+C to Exit) ===")
            print("-" * 65)
            print(f"{'Device Name':<25} | {'RSSI':<8} | {'Signal Graph'}")
            print("-" * 65)
            
            # Get all objects from BlueZ
            mngr = bus.get("org.bluez", "/")
            objs = mngr.GetManagedObjects()
            
            # Map for sorting and display
            named_list = []
            
            for path, interfaces in objs.items():
                if "org.bluez.Device1" in interfaces:
                    props = interfaces["org.bluez.Device1"]
                    name = props.get("Name", props.get("Alias", None))
                    # Only show named devices as requested
                    if name and not name.startswith("00-00-00"): # Basic filter for no-name/MAC-only
                        rssi = props.get("RSSI", -100)
                        named_list.append((name, path.split('/')[-1].replace('dev_', '').replace('_', ':'), rssi))
            
            # Sort by RSSI (strongest first)
            named_list.sort(key=lambda x: x[2], reverse=True)
            
            for name, addr, rssi in named_list:
                bar_len = max(0, min(30, (rssi + 110) // 3))
                bar = "█" * bar_len + "-" * (30 - bar_len)
                print(f"{name[:25]:<25} | {rssi:>4} dBm | {bar}")
            
            if not named_list:
                print("\n[!] No named devices found yet. Still scanning...")
                
            time.sleep(1) # Refresh rate
            
    except KeyboardInterrupt:
        print("\n[!] Dashboard stopped.")
    except Exception as e:
        print(f"\nDashboard Error: {e}")
    finally:
        if adapter:
            try: adapter.StopDiscovery()
            except: pass
from utils.adapter_stealth import set_mac_address, set_impersonation, reset_stealth

file_lock = threading.Lock()

def save_paired_device(addr, name, filename='paired_devices.txt'):
    """Log successfully paired devices to a file."""
    with file_lock:
        with open(filename, 'a') as file:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            file.write(f"[{timestamp}] {addr} | {name}\n")

def get_target_address():
    target_address = input("\nSelect a device (number), 'm' for Proximity Map, 'b' for BLAST ALL, or '3' for Stealth Settings: ").strip().lower()

    if target_address == "3":
        return "GO_STEALTH"

    if target_address == "":
        devices = scan_for_devices()
        if devices:
            # Show list of scanned devices for user selection
            while True:
                # Separate named from unknown for display consistency
                named_devices = [d for d in devices if not d[1].startswith("[Unknown Device]")]
                unknown_devices = [d for d in devices if d[1].startswith("[Unknown Device]")]
                
                print("\nDiscovered Devices:")
                for idx, (addr, name) in enumerate(named_devices):
                    print(f"{idx + 1}: Name: {name} | Address: {addr}")
                
                other_idx = len(named_devices) + 1
                if unknown_devices:
                    print(f"{other_idx}: -- Show Unknown Devices ({len(unknown_devices)} items) --")
                
                print("\nOptions:")
                print(" 'm' - Proximity Map")
                print(" 'b' - BLAST ALL Discovered Devices")
                print(" Enter to exit")
                
                try:
                    selection_input = input("\nSelect (number/m/b): ").strip().lower()
                    if not selection_input:
                        print("\nNo selection made. Exiting.")
                        return None
                    
                    if selection_input == 'm':
                        track_all_named_rssi()
                        continue

                    if selection_input == 'b':
                        # Return special flag for BLAST ALL
                        return "BLAST_ALL", devices

                    selection = int(selection_input) - 1
                    
                    chosen_device = None
                    if 0 <= selection < len(named_devices):
                        chosen_device = named_devices[selection]
                    elif selection == len(named_devices) and unknown_devices:
                        print("\nUnknown Devices:")
                        for idx, (addr, name) in enumerate(unknown_devices):
                            print(f"{idx + 1}: Name: {name} | Address: {addr}")
                        sub_choice = input(f"\nSelect an unknown device (1-{len(unknown_devices)}): ").strip()
                        if sub_choice.isdigit():
                            s_idx = int(sub_choice) - 1
                            if 0 <= s_idx < len(unknown_devices):
                                chosen_device = unknown_devices[s_idx]
                    
                    if chosen_device:
                        addr = chosen_device[0]
                        name = chosen_device[1]
                        
                        print(f"\nTarget Selected: {name}")
                        print(f"Address: {addr}")
                        print("-" * 25)
                        print(" 1: Attack (Deliver Payload)")
                        print(" 2: Discover Services (UUIDs)")
                        print(" 3: Proximity (Single RSSI)")
                        print(" 4: Back to List")
                        print("\n Or Global Actions:")
                        print(" 'b': BLAST ALL Discovered")
                        print(" 'm': Global Proximity Map")
                        
                        action = input("\nSelect choice (1-4/b/m): ").strip().lower()
                        if action == "1":
                            return addr
                        elif action == "2":
                            get_services(addr)
                            input("\nPress Enter to return to device list...")
                            continue 
                        elif action == "3":
                            track_rssi(addr)
                            input("\nPress Enter to return to device list...")
                            continue
                        elif action == "b":
                            return "BLAST_ALL", devices
                        elif action == "m":
                            track_all_named_rssi()
                            continue
                        else:
                            continue 
                    else:
                        print("\nInvalid selection. Try again.")
                        continue
                except ValueError:
                    print("\nInvalid input. Please enter a valid number or option.")
                    continue
        else:
            return None
    elif not is_valid_mac_address(target_address):
        print("\nInvalid MAC address format. Please enter a valid MAC address.")
        return None

    return target_address

def restart_bluetooth_daemon():
    run(["sudo", "service", "bluetooth", "restart"])
    time.sleep(0.5)

def run(command):
    assert(isinstance(command, list))
    log.info("executing '%s'" % " ".join(command))
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result

def print_fancy_ascii_art():
    cyan = "\033[96m"
    blue = "\033[94m"
    reset = "\033[0m"
    
    # Using a standard string and joining to avoid f-string backslash issues
    lines = [
        "                .___________.",
        "        (O)____/  " + blue + "_________  " + cyan + "\\____(O)",
        "              /  " + blue + "/         \\ " + cyan + " \\",
        "       (O)___/  " + blue + "/           \\ " + cyan + " \\___(O)",
        "            /  " + blue + "/             \\ " + cyan + " \\",
        "      (O)__/  " + blue + "/     /\\     " + blue + "\\ " + cyan + " \\__(O)",
        "           \\  " + blue + "\\    /  \\    / " + cyan + " /",
        "            \\  " + blue + "\\  /    \\  / " + cyan + " /",
        "             \\  " + blue + "\\/      \\/ " + cyan + " /",
        "              \\           /",
        "               \\_________/",
        "",
        "       " + blue + "Elite Bluetooth Testing & Attacker",
        "          v3.0 - Blast Mode" + reset
    ]
    
    print(cyan)
    for line in lines:
        print(line)
    print(reset)

def clear_screen():
    os.system('clear')

# Function to save discovered devices to a file
def save_devices_to_file(devices, filename='known_devices.txt'):
    with open(filename, 'w') as file:
        for addr, name in devices:
            file.write(f"{addr},{name}\n")

def get_yes_no():
    stdscr = curses.initscr()
    curses.cbreak()
    stdscr.keypad(1)

    while True:
        key = stdscr.getch()
        if key == ord('y'):
            response = 'yes'
            break
        elif key == ord('n'):
            response = 'no'
            break

    curses.endwin()
    return response

def perform_deep_scan(duration_classic=8, duration_ble=5):
    """Core Deep Scan engine (Classic + BLE). Returns dict of {addr: name}."""
    unique_devices = {}
    
    # 1. Classic Scan
    log.info(f"Scanning Classic Bluetooth ({duration_classic}s)...")
    try:
        nearby_classic = bluetooth.discover_devices(duration=duration_classic, lookup_names=True, flush_cache=True, lookup_class=True)
        for addr, name, _ in nearby_classic:
            unique_devices[addr] = name if name else f"[Unknown Device] {get_vendor(addr)}"
    except Exception as e:
        log.warning(f"Classic scan failed: {e}")

    # 2. BLE Scan
    log.info(f"Checking for BLE devices ({duration_ble}s)...")
    try:
        # Use a non-blocking approach for lescan
        lescan_proc = subprocess.Popen(["sudo", "hcitool", "lescan", "--duplicates"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(duration_ble)
        os.kill(lescan_proc.pid, signal.SIGINT)
        
        stdout, _ = lescan_proc.communicate()
        for line in stdout.decode('utf-8', errors='ignore').split('\n'):
            line = line.strip()
            if line and "LE Scan" not in line:
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    addr, name = parts
                    if addr not in unique_devices or not unique_devices[addr]:
                        unique_devices[addr] = name if name != "(unknown)" else f"[Unknown Device] {get_vendor(addr)}"
    except Exception as e:
        log.warning(f"BLE scan failed: {e}")
        
    return unique_devices

# Function to scan for devices
def scan_for_devices():
    main_menu()

    # Load known devices
    known_devices = load_known_devices()
    if known_devices:
        known_named = [d for d in known_devices if not d[1].startswith("[Unknown Device]")]
        known_unknown = [d for d in known_devices if d[1].startswith("[Unknown Device]")]
        
        if known_named:
            print("\nKnown devices (Named):")
            for idx, (addr, name) in enumerate(known_named):
                print(f"{idx + 1}: Name: {name} | Address: {addr}")

            use_known = input("\nUse one of these named devices? (yes/no/other): ").lower()
            if use_known == 'yes':
                choice = int(input("Enter number: "))
                return [known_named[choice - 1]]
            elif use_known == 'other' and known_unknown:
                print("\nKnown devices (Unknown):")
                for idx, (addr, name) in enumerate(known_unknown):
                    print(f"{idx + 1}: Address: {addr}")
                choice = int(input("Enter number: "))
                return [known_unknown[choice - 1]]
        elif known_unknown:
            use_other = input(f"\nYou have {len(known_unknown)} unknown devices saved. See them? (yes/no): ").lower()
            if use_other == 'yes':
                for idx, (addr, name) in enumerate(known_unknown):
                    print(f"{idx + 1}: Address: {addr}")
                choice = int(input("Enter number: "))
                return [known_unknown[choice - 1]]

    print("\nSelect Scan Mode:")
    print("1: Quick Scan (Classic Only, Original Method)")
    print("2: Deep Scan (Classic + BLE, with Vendor Identification)")
    scan_choice = input("Enter choice (1/2): ")

    if scan_choice == "1":
        # ORIGINAL METHOD - DO NOT EDIT
        print("\nAttempting to scan now...")
        nearby_devices = bluetooth.discover_devices(duration=8, lookup_names=True, flush_cache=True, lookup_class=True)
        device_list = []
        if len(nearby_devices) == 0:
            print("\nNo nearby devices found.")
        else:
            print("\nFound {} nearby device(s):".format(len(nearby_devices)))
            for idx, (addr, name, _) in enumerate(nearby_devices):
                device_list.append((addr, name))

        # Save the scanned devices only if they are not already in known devices
        new_devices = [device for device in device_list if device not in known_devices]
        if new_devices:
            known_devices += new_devices
            save_devices_to_file(known_devices)
            for idx, (addr, name) in enumerate(new_devices):
                print(f"{idx + 1}: Device Name: {name} | Address: {addr}")
        return device_list

    else:
        # DEEP SCAN METHOD (Nagamancayy Edition)
        print("\n[!] Starting Deep Scan (Classic + BLE)...")
        unique_devices = perform_deep_scan()
        
        device_list = []
        for addr, name in unique_devices.items():
            device_list.append((addr, name))
        
        # Save the scanned devices
        new_devices = [device for device in device_list if device not in known_devices]
        if new_devices:
            known_devices += new_devices
            save_devices_to_file(known_devices)
        
        return device_list

        # 3. RSSI Background Check
        print("Gathering signal strength (RSSI)...")
        device_rssi = {} # {addr: rssi}
        try:
            rssi_proc = subprocess.run(["sudo", "btmgmt", "find"], capture_output=True, text=True, timeout=2)
            for line in rssi_proc.stdout.splitlines():
                if "rssi" in line.lower():
                    # Parse line like: dev_found: 00:11:22:33:44:55 type BR/EDR rssi -60 ...
                    parts = line.split()
                    addr = next((p for p in parts if is_valid_mac_address(p)), None)
                    if addr:
                        rssi_val = line.split('rssi')[-1].split()[0]
                        device_rssi[addr.upper()] = rssi_val
        except:
            pass

        # 4. Finalize list with Names, OUI guesses, and RSSI
        print(f"Finalizing {len(unique_devices)} unique devices...")
        device_list = []
        for addr, name in unique_devices.items():
            final_name = name
            
            if not final_name:
                resolved = resolve_name(addr)
                if resolved: final_name = resolved
            
            display_name = final_name if final_name else f"[{get_vendor(addr)}]"
            
            # Add RSSI to display name if found
            rssi = device_rssi.get(addr.upper())
            if rssi:
                display_name = f"{display_name} [RSSI: {rssi}]"
                
            device_list.append((addr, display_name))
        
        if not device_list:
            print("\nNo nearby devices found.")
        else:
            # SAVE DISCOVERED DEVICES IMMEDIATELY (Fix persistence)
            new_discovered = [d for d in device_list if d not in known_devices]
            if new_discovered:
                known_devices += new_discovered
                save_devices_to_file(known_devices)
                print(f"[+] Saved {len(new_discovered)} new devices to known_devices.txt")

            # Smart Filtering: Separate named from unknown
            named_devices = [d for d in device_list if not d[1].startswith("[Unknown Device]")]
            unknown_devices = [d for d in device_list if d[1].startswith("[Unknown Device]")]
            
            print("\nFound {} unique device(s) with names:".format(len(named_devices)))
            for idx, (addr, name) in enumerate(named_devices):
                print(f"{idx + 1}: Name: {name} | Address: {addr}")
            
            if unknown_devices:
                other_idx = len(named_devices) + 1
                print(f"{other_idx}: -- Show Unknown Devices ({len(unknown_devices)} items) --")
                
                try:
                    choice = input("\nSelect a device (or Enter for unknown list): ").strip()
                    if not choice: # User just pressed enter, or wants unknown
                        print("\nShowing Unknown Devices:")
                        for idx, (addr, name) in enumerate(unknown_devices):
                            print(f"{idx + 1}: Name: {name} | Address: {addr}")
                        
                        sub_choice = input(f"\nSelect an unknown device by number (1-{len(unknown_devices)}): ").strip()
                        if sub_choice.isdigit():
                            s_idx = int(sub_choice) - 1
                            if 0 <= s_idx < len(unknown_devices):
                                return [unknown_devices[s_idx]]
                        return []
                    
                    if choice.isdigit():
                        c_idx = int(choice) - 1
                        if c_idx == len(named_devices) and unknown_devices:
                            # User specifically chose the "Show Unknown" option
                            print("\nShowing Unknown Devices:")
                            for idx, (addr, name) in enumerate(unknown_devices):
                                print(f"{idx + 1}: Name: {name} | Address: {addr}")
                            sub_choice = input(f"\nSelect an unknown device by number (1-{len(unknown_devices)}): ").strip()
                            if sub_choice.isdigit():
                                s_idx = int(sub_choice) - 1
                                if 0 <= s_idx < len(unknown_devices):
                                    return [unknown_devices[s_idx]]
                            return []
                        elif 0 <= c_idx < len(named_devices):
                            return [named_devices[c_idx]]
                except ValueError:
                    pass
            
            return device_list

    return []

def print_menu():
    title = "ELITE BLUETOOTH TESTING & ATTACKER"
    separator = "=" * 70
    print("\033[1;35m" + separator)  # Purple color for separator
    print("\033[1;33m" + title.center(len(separator)))  # Yellow color for title
    print("\033[1;35m" + separator + "\033[0m")  # Purple color for separator
    print("\033[1;32m" + "卄ﾑ𝖈𝗸╰Ꮗⁱ‿ᵗ𝔥╯ﾑ𝗸𝗸！| you can still attack devices without visibility..." + "\033[0m")
    print("\033[1;32m" + "If you have their MAC address..." + "\033[0m")
    print("\033[1;33m" + "3: Stealth & Impersonation Settings (EXPERIMENTAL)" + "\033[0m")
    print("\033[1;35m" + separator + "\033[0m")  # Purple color for separator

def stealth_menu(adapter_id):
    """Sub-menu for managing adapter stealth and identity."""
    while True:
        clear_screen()
        print_fancy_ascii_art()
        print("\033[1;36m" + "=== STEALTH & IMPERSONATION SETTINGS ===" + "\033[0m")
        print("1: Randomize MAC Address (Stealth)")
        print("2: Impersonate Sony DualSense (Gamepad)")
        print("3: Impersonate Logitech K810 (Keyboard)")
        print("4: Impersonate Owner's iPhone (Phone)")
        print("5: Reset Adapter (Restore Identity)")
        print("q: Back to Main Menu")
        
        choice = input("\nSelect an option: ").lower().strip()
        
        if choice == '1':
            set_mac_address(adapter_id)
            input("\nPress Enter to continue...")
        elif choice == '2':
            set_impersonation(adapter_id, "Sony")
            input("\nPress Enter to continue...")
        elif choice == '3':
            set_impersonation(adapter_id, "Logitech")
            input("\nPress Enter to continue...")
        elif choice == '4':
            set_impersonation(adapter_id, "Apple")
            input("\nPress Enter to continue...")
        elif choice == '5':
            reset_stealth(adapter_id)
            input("\nPress Enter to continue...")
        elif choice == 'q':
            break

def main_menu():
    clear_screen()
    print_fancy_ascii_art()
    print_menu()


def is_valid_mac_address(mac_address):
    # Regular expression to match a MAC address in the form XX:XX:XX:XX:XX:XX
    mac_address_pattern = re.compile(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$')
    return mac_address_pattern.match(mac_address) is not None

# Function to read DuckyScript from file
def read_duckyscript(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            return [line.strip() for line in file.readlines()]
    else:
        log.warning(f"File {filename} not found. Skipping DuckyScript.")
        return None

# Function to load known devices from a file
def load_known_devices(filename='known_devices.txt'):
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            return [tuple(line.strip().split(',')) for line in file]
    else:
        return []
