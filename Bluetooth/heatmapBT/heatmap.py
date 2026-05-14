import asyncio, csv, datetime, sys
from bleak import BleakScanner

TARGET_MAC = "9C:9E:D5:92:22:24"
LOG_FILE = "bt_heatmap.csv"

async def scan(label):
    results = await BleakScanner.discover(timeout=5.0, return_adv=True)
    # results is a dict: {mac: (BLEDevice, AdvertisementData)}
    
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        for mac, (device, adv) in results.items():
            if mac.upper() == TARGET_MAC.upper():
                rssi = adv.rssi
                row = [datetime.datetime.now(), label, rssi]
                writer.writerow(row)
                print(f"[{label}] {device.name} RSSI: {rssi} dBm")
                return
    
    print(f"[{label}] Device not found during scan")

label = sys.argv[1] if len(sys.argv) > 1 else "unknown"
for i in range(5):
    asyncio.run(scan(label=label))
