import subprocess
import random
import time
import logging
log = logging.getLogger(__name__)

def run_cmd(cmd):
    """Utility to run a command and return output."""
    try:
        result = subprocess.run(cmd, shell=False, capture_output=True, text=True)
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)

def set_mac_address(iface, new_mac=None):
    """
    Spoof the MAC address of the adapter. 
    Requires 'bdaddr' (part of bluez-tools) or 'btmgmt'.
    """
    if not new_mac:
        # Generate random MAC
        new_mac = "00:1A:7D:%02X:%02X:%02X" % (
            random.randint(0, 255),
            random.randint(0, 255),
            random.randint(0, 255)
        )
    
    log.info(f"[STEALTH] Attempting to spoof MAC to: {new_mac}")
    
    # Method 1: bdaddr (Most reliable for CSR 4.0)
    success, _ = run_cmd(["sudo", "bdaddr", "-i", iface, new_mac])
    if success:
        log.notice(f"[STEALTH] MAC address successfully changed to {new_mac}")
        # Need to reset adapter for change to take effect
        run_cmd(["sudo", "hciconfig", iface, "reset"])
        return True, new_mac

    # Method 2: btmgmt (if supported by kernel/driver)
    # btmgmt requires being down first
    run_cmd(["sudo", "btmgmt", "-i", iface, "power", "off"])
    success, _ = run_cmd(["sudo", "btmgmt", "-i", iface, "public-addr", new_mac])
    run_cmd(["sudo", "btmgmt", "-i", iface, "power", "on"])
    
    if success:
        log.notice(f"[STEALTH] MAC address changed via btmgmt to {new_mac}")
        return True, new_mac
        
    log.warning("[STEALTH] Failed to change MAC address. Hardware might not support it.")
    return False, None

def set_impersonation(iface, profile_name):
    """
    Spoof the Class of Device (CoD) and Adapter Name.
    Profiles: 'Sony', 'Logitech', 'Apple'
    """
    profiles = {
        "Sony": {"class": "0x002508", "name": "Wireless Controller"},
        "Logitech": {"class": "0x000540", "name": "Logitech K810"},
        "Apple": {"class": "0x000204", "name": "Owner's iPhone"}
    }
    
    if profile_name not in profiles:
        return False
        
    config = profiles[profile_name]
    log.info(f"[STEALTH] Impersonating: {profile_name} (Class: {config['class']})")
    
    # 1. Set Class of Device
    run_cmd(["sudo", "hciconfig", iface, "class", config["class"]])
    run_cmd(["sudo", "btmgmt", "-i", iface, "class", config["class"]])
    
    # 2. Set Local Name
    run_cmd(["sudo", "hciconfig", iface, "name", config["name"]])
    run_cmd(["sudo", "btmgmt", "-i", iface, "name", config["name"]])
    
    log.notice(f"[STEALTH] Identity successfully set to '{config['name']}'")
    return True

def reset_stealth(iface):
    """Reset adapter properties to default."""
    log.info("[STEALTH] Resetting adapter to default state...")
    run_cmd(["sudo", "hciconfig", iface, "reset"])
    run_cmd(["sudo", "btmgmt", "-i", iface, "power", "off"])
    run_cmd(["sudo", "btmgmt", "-i", iface, "power", "on"])
    return True
