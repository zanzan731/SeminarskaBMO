import subprocess
import re

def ping_bluetooth(mac_address, count=2000, device="hci0"):
    cmd = ['l2ping', '-c', str(count), '-i', str(device), '-f', mac_address]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    times = []
    for line in result.stdout.split('\n'):
        match = re.search(r'time\s+([\d\.]+)ms', line)
        if match:
            times.append(float(match.group(1)))
    
    if times:
        print(f"Min: {min(times):.2f} ms")
        print(f"Avg: {sum(times)/len(times):.2f} ms")
        print(f"Max: {max(times):.2f} ms")
    else:
        print("No ping responses received.")

ping_bluetooth('74:EF:4B:B9:3A:DC')
