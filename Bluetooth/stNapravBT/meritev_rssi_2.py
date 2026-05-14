import asyncio
import csv
import datetime
from bleak import BleakScanner

LOG_FILE = "test.csv"
results = {}


def callback(device, adv):
    results[device.address] = (device, adv)

async def auto_discover_and_log():
    print("Starting discovery... Press Ctrl+C to stop.")
    
    # Initialize CSV header if file doesn't exist
    try:
        with open(LOG_FILE, "x", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Device_Name", "MAC_Address", "RSSI"])
    except FileExistsError:
        pass

    while True:
        print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] Scanning for devices...")
        
        results.clear()
        # Discover all nearby BLE devices
        # return_adv=True gives us access to the RSSI and advertising data
        async with BleakScanner(detection_callback=callback, scanning_mode="active") as scanner:
            await asyncio.sleep(7.0)

        devices = results

        if not devices:
            print("No devices found in this cycle.")
        
        with open(LOG_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            
            for mac, (device, adv) in devices.items():
                if device.name:
                    name = device.name
                else:
                    continue
                rssi = adv.rssi
                
                # Log to console
                print(f"Found: {name} | MAC: {mac} | RSSI: {rssi}dBm")
                
                # Log to CSV
                writer.writerow([datetime.datetime.now(), name, mac, rssi])
        
        # Optional: Add a small delay between scan cycles to prevent CPU spikes
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(auto_discover_and_log())
    except KeyboardInterrupt:
        print("\nScanner stopped by user.")
