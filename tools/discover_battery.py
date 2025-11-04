#!/usr/bin/env python3
"""
BLE Characteristic Discovery Script

This script connects to your door device and lists ALL BLE services
and characteristics, helping you find the battery characteristic UUID.

Usage:
    1. Edit MAC_ADDRESS below with your door's MAC
    2. Run: python3 discover_battery.py
    3. Look for Battery Service (0x180F) or characteristics with "read" property
"""

import asyncio
import sys
from bleak import BleakClient, BleakScanner

# ============================================================
# CONFIGURATION - EDIT THIS
# ============================================================
MAC_ADDRESS = "00:80:E1:22:EE:F2"  # Replace with your door's MAC address
# ============================================================


async def discover_characteristics():
    """Discover all BLE services and characteristics."""
    
    print("=" * 70)
    print(f"BLE Device Discovery: {MAC_ADDRESS}")
    print("=" * 70)
    print()
    
    # Step 1: Scan for device
    print(f"[1/3] Scanning for device...")
    device = await BleakScanner.find_device_by_address(MAC_ADDRESS, timeout=10.0)
    
    if not device:
        print("❌ Device not found!")
        print()
        print("Troubleshooting:")
        print("  1. Check MAC address is correct")
        print("  2. Ensure door device is powered on")
        print("  3. Check Bluetooth is enabled: systemctl status bluetooth")
        print("  4. Try scanning manually: sudo hcitool lescan")
        return False
    
    print(f"✓ Found device: {device.name or 'Unknown'}")
    print()
    
    # Step 2: Connect
    print(f"[2/3] Connecting to device...")
    try:
        async with BleakClient(MAC_ADDRESS, timeout=15.0) as client:
            print("✓ Connected!")
            print()
            
            # Step 3: Enumerate services and characteristics
            print(f"[3/3] Discovering services and characteristics...")
            print()
            print("=" * 70)
            
            service_count = 0
            char_count = 0
            battery_found = False
            
            for service in client.services:
                service_count += 1
                
                # Highlight battery service
                is_battery = "180f" in service.uuid.lower()
                marker = "🔋 BATTERY SERVICE" if is_battery else ""
                
                print(f"\n📦 Service: {service.uuid} {marker}")
                print(f"   Description: {service.description}")
                
                for char in service.characteristics:
                    char_count += 1
                    
                    # Highlight battery characteristic
                    is_battery_char = "2a19" in char.uuid.lower()
                    char_marker = "🔋 BATTERY LEVEL" if is_battery_char else ""
                    
                    print(f"\n   📝 Characteristic: {char.uuid} {char_marker}")
                    print(f"      Description: {char.description}")
                    print(f"      Properties: {', '.join(char.properties)}")
                    
                    # Try to read if readable
                    if "read" in char.properties:
                        try:
                            value = await client.read_gatt_char(char.uuid)
                            print(f"      ✓ Read successful!")
                            print(f"         Raw (hex): {value.hex()}")
                            print(f"         Raw (bytes): {list(value)}")
                            
                            # Try common interpretations
                            if len(value) == 1:
                                print(f"         As uint8: {value[0]}")
                                if 0 <= value[0] <= 100:
                                    print(f"         👉 Looks like battery percentage: {value[0]}%")
                                    battery_found = True
                            elif len(value) == 2:
                                print(f"         As uint16 (little-endian): {int.from_bytes(value, 'little')}")
                                print(f"         As uint16 (big-endian): {int.from_bytes(value, 'big')}")
                        except Exception as e:
                            print(f"      ✗ Could not read: {e}")
                    else:
                        print(f"      (not readable)")
            
            print()
            print("=" * 70)
            print(f"\n📊 Summary:")
            print(f"   Services found: {service_count}")
            print(f"   Characteristics found: {char_count}")
            
            if battery_found:
                print(f"   🔋 Battery characteristic found! (see above)")
            else:
                print(f"   ⚠️  No obvious battery characteristic found")
                print(f"      Check characteristics with 'read' property above")
            
            print()
            return True
            
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print()
        print("Troubleshooting:")
        print("  1. Device might be connected elsewhere (close other apps)")
        print("  2. Increase timeout if connection is slow")
        print("  3. Check Bluetooth adapter: hciconfig")
        return False


def print_usage_instructions():
    """Print instructions for using the discovered data."""
    print("=" * 70)
    print("Next Steps:")
    print("=" * 70)
    print()
    print("1. If you found a battery characteristic (marked with 🔋):")
    print("   - Copy the UUID (e.g., 00002a19-0000-1000-8000-00805f9b34fb)")
    print("   - Test it with: python3 test_battery.py")
    print()
    print("2. If no battery characteristic found:")
    print("   - Look for characteristics with 'read' property")
    print("   - Look for values in range 0-100")
    print("   - Try custom characteristics (non-standard UUIDs)")
    print()
    print("3. Standard Battery Service UUIDs:")
    print("   Service:        0000180f-0000-1000-8000-00805f9b34fb")
    print("   Characteristic: 00002a19-0000-1000-8000-00805f9b34fb")
    print()
    print("4. Your door's write characteristic (for reference):")
    print("   00000000-8e22-4541-9d4c-21edae82ed19")
    print()
    print("See BATTERY_IMPLEMENTATION.md for complete implementation guide.")
    print()


async def main():
    try:
        success = await discover_characteristics()
        if success:
            print_usage_instructions()
            return 0
        else:
            return 1
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        MAC_ADDRESS = sys.argv[1]
        print(f"Using MAC from command line: {MAC_ADDRESS}")
    
    sys.exit(asyncio.run(main()))
