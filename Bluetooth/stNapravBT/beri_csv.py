import csv
from tabulate import tabulate

target_name = "Unknown"
input_file = "rssi_meritve_auto.csv"

data = []

# 1. Read and filter data
try:
    with open(input_file, mode='r') as f_in:
        reader = csv.DictReader(f_in)
        for row in reader:
            # Filtering logic (optional - remove if block to show all)
            if row['Device_Name'] != target_name:
            #if row['MAC_Address'] == "F8:AB:E5:68:83:FA":
                # Convert RSSI to integer for proper numerical sorting
                row['RSSI'] = int(row['RSSI']) if row['RSSI'] else -100
                data.append(row)
except FileNotFoundError:
    print(f"Error: {input_file} not found.")
    exit()

# 2. Sorting the data
# Sort by RSSI (descending = strongest signal first)
# To sort by Timestamp, change 'RSSI' to 'Timestamp'
sorted_data = sorted(data, key=lambda x: x['RSSI'], reverse=True)

# 3. Display in a nice table
if sorted_data:
    print(f"\nFiltered Results for: {target_name}")
    print(tabulate(sorted_data, headers="keys", tablefmt="fancy_grid"))
else:
    print("No matching data found.")
