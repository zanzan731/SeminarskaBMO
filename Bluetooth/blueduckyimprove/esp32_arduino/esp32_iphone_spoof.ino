/*
 * ESP32 BLE Spoofing Example - iPhone Edition 🦆📱
 * part of the BlueDucky-Improve project (Educational Purposes Only)
 *
 * This sketch makes your ESP32 appear as an Apple device in BLE scans.
 * It broadcasts Apple's Manufacturer ID (0x004C).
 */

#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>

// Apple Manufacturer ID = 0x004C
// Data format for "Nearby" or "Find My" often follows specific 
// patterns that make it appear as an iPhone.
uint8_t apple_data[] = {
  0x4C, 0x00, // Apple ID
  0x02,       // Type: Nearby
  0x15,       // Length
  0xDE, 0xAD, 0xBE, 0xEF, 0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88, 0x99, 0xAA, 0xBB, // Proximity UUID (Sample)
  0x00, 0x01, // Major
  0x00, 0x02, // Minor
  0xC5        // TX Power
};

void setup() {
  Serial.begin(115200);
  Serial.println("Starting ESP32 BLE Spoofing...");

  // Initialize the BLE device
  // You can set the name to anything, e.g., "iPhone 15 Pro"
  BLEDevice::init("iPhone 15 Pro");

  // Create the BLE Server
  BLEServer *pServer = BLEDevice::createServer();

  // Create Advertising object
  BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();

  // Set Manufacturer Data
  std::string mData((char*)apple_data, sizeof(apple_data));
  pAdvertising->setManufacturerData(mData);

  // Appearance 64 = Generic Phone (Standard BLE ID)
  pAdvertising->setAppearance(64);

  // Optimization for discovery
  pAdvertising->setScanResponse(true);
  pAdvertising->setMinPreferred(0x06);  // functions that help with iPhone connections
  pAdvertising->setMinPreferred(0x12);

  // Start advertising
  BLEDevice::startAdvertising();
  Serial.println("Advertising as 'iPhone 15 Pro' now!");
}

void loop() {
  // Just keep advertising
  delay(2000);
}
