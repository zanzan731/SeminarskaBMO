#!/usr/bin/env python3

import dbus
import sys

def download_phonebook(device_address):
    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object('org.bluez.obex', '/org/bluez/obex'),
                             'org.bluez.obex.Client1')
    session_path = manager.CreateSession({'Destination': device_address, 'Target': 'PBAP'})
    session = dbus.Interface(bus.get_object('org.bluez.obex', session_path),
                             'org.bluez.obex.Session1')
    pb_path = session.PullPhonebook({'PhoneBook': 'SIM'})
    return session.Retrieve(pb_path)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <device_mac>")
        sys.exit(1)
    data = download_phonebook(sys.argv[1])
    with open('phonebook.vcf', 'wb') as f:
        f.write(data)
    print("Phonebook downloaded to phonebook.vcf")
