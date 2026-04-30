# ESP32 BLE iPhone Spoofing 🦆📱

This folder contains a standalone Arduino sketch (`.ino`) for the **ESP32** (standard DevKit V1) that allows it to masquerade as an Apple device (iPhone) over BLE.

## 🛠️ Requirements
- **Hardware**: ESP32 DevKit V1 (Standard, not S2/S3 for best compatibility).
- **Software**: Arduino IDE.
- **Library**: `BLEDevice` (Built-in for ESP32).

## 🚀 How to Use
1.  Open `esp32_iphone_spoof.ino` in your **Arduino IDE**.
2.  Install the ESP32 board manager if you haven't already.
3.  Select your board (e.g., **DOIT ESP32 DEVKIT V1**).
4.  Click **Upload**.
5.  Once uploaded, open your **BlueDucky** tool on Kali Linux and run **Option 2 (Deep Scan)**.
6.  You should see your ESP32 appearing as an **`iPhone 15 Pro`** (or with an Apple Vendor tag).

## 🔍 How it Works
The code uses the `0x004C` Manufacturer ID, which is registered to **Apple Inc.** Most Bluetooth scanners (including BlueDucky's Deep Scan) see this ID and immediately identify the device as an Apple product.

---
*Educational use only. Stay safe and ethical!* 🦆🦾
