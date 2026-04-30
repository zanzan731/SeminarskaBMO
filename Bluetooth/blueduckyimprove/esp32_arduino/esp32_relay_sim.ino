/*
 * ESP32 BLE Relay Simulation Firmware 🛡️🚘
 * Part of BlueDucky-Improve Suite
 *
 * This firmware allows the ESP32 to toggle between:
 * 1. Car-Beacon Mode: Mimics vehicle BLE advertisements
 * 2. Key-Spoof Mode: Mimics a phone-key looking for a car
 *
 * Use Serial Monitor (115200 baud) to switch modes:
 * Type '1' for Car-Beacon (Tesla-style)
 * Type '2' for Key-Spoof (iPhone-style)
 */

#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Keypad.h>

// --- Hardware Configuration ---
// LCD I2C Setup (Address 0x27 or 0x3F)
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Keypad 4x4 Setup
const byte ROWS = 4;
const byte COLS = 4;
char keys[ROWS][COLS] = {
  {'1','2','3','A'},
  {'4','5','6','B'},
  {'7','8','9','C'},
  {'*','0','#','D'}
};
byte rowPins[ROWS] = {13, 12, 14, 27}; 
byte colPins[COLS] = {26, 25, 33, 32};
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

// --- BLE Configuration ---
bool isCarMode = true;
#define TESLA_SERVICE_UUID "00000211-0000-1000-8000-00805f9b34fb"

void updateLCD(String line1, String line2) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(line1);
  lcd.setCursor(0, 1);
  lcd.print(line2);
}

void startAdvertising(bool carMode) {
  BLEDevice::deinit();
  delay(200);
  
  if (carMode) {
    BLEDevice::init("Vehicle Beacon");
    updateLCD("MODE: CAR-BEACON", "Simulating Tesla");
    BLEServer *pServer = BLEDevice::createServer();
    BLEService *pService = pServer->createService(TESLA_SERVICE_UUID);
    pService->start();
    
    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(TESLA_SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    BLEDevice::startAdvertising();
  } else {
    BLEDevice::init("Owner's iPhone");
    updateLCD("MODE: KEY-SPOOF", "Owner Device");
    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->setAppearance(64); 
    pAdvertising->setScanResponse(true);
    BLEDevice::startAdvertising();
  }
}

void setup() {
  Serial.begin(115200);
  
  // Initialize LCD
  lcd.init();
  lcd.backlight();
  updateLCD("BlueDucky Relay", "System Ready...");
  delay(1500);

  startAdvertising(isCarMode);
}

void loop() {
  char key = keypad.getKey();
  
  if (key) {
    Serial.print("Key Pressed: ");
    Serial.println(key);
    
    if (key == '1') {
      isCarMode = true;
      startAdvertising(isCarMode);
    } else if (key == '2') {
      isCarMode = false;
      startAdvertising(isCarMode);
    } else if (key == '0') {
      updateLCD("BlueDucky Relay", "IDLE - Stop BLE");
      BLEDevice::deinit();
    }
  }

  // Also support Serial for backward compatibility
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd == '1') { isCarMode = true; startAdvertising(isCarMode); }
    if (cmd == '2') { isCarMode = false; startAdvertising(isCarMode); }
  }
}
