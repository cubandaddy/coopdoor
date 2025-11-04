#!/usr/bin/env python3
"""
G-80 Battery Test Script

This script tests battery reading on the G-80 coop door device.
Battery is located at byte 48 of the status characteristic.

Usage:
    python3 test_battery_g80.py              # Single reading
    python3 test_battery_g80.py --monitor    # Continuous monitoring (5 min)
"""

import asyncio
import sys
from datetime import datetime

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    print("ERROR: bleak library not installed")
    print("Install with: pip install bleak --break-system-packages")
    sys.exit(1)

# G-80 Configuration
MAC_ADDRESS = "00:80:E1:22:EE:F2"
CHAR_BATTERY = "00000001-8e22-4541-9d4c-21edae82ed19"  # Status characteristic
BATTERY_BYTE_OFFSET = 48  # Battery at byte 48


async def read_battery_once():
    """Read battery once and display."""
    
    print("\n" + "=" * 70)
    print("G-80 Battery Test")
    print("=" * 70)
    
    print(f"\nScanning for {MAC_ADDRESS}...")
    device = await BleakScanner.find_device_by_address(MAC_ADDRESS, timeout=10.0)
    
    if not device:
        print("❌ Device not found!")
        return False
    
    print(f"✓ Found: {device.name or 'G-80'}")
    print("Connecting...")
    
    try:
        async with BleakClient(MAC_ADDRESS, timeout=20.0, address_type="public") as client:
            print("✓ Connected!\n")
            
            # Read status packet
            value = await client.read_gatt_char(CHAR_BATTERY)
            
            if len(value) > BATTERY_BYTE_OFFSET:
                battery = value[BATTERY_BYTE_OFFSET]
                
                print("=" * 70)
                print("🔋 BATTERY READING")
                print("=" * 70)
                print(f"Battery Level: {battery}%")
                print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"Status Packet: {len(value)} bytes")
                print("=" * 70)
                print("\n✓ Battery monitoring works!\n")
                
                return True
            else:
                print(f"❌ Status packet too short: {len(value)} bytes")
                return False
                
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return False


async def monitor_battery():
    """Monitor battery continuously for 5 minutes."""
    
    print("\n" + "=" * 70)
    print("G-80 Battery Monitor - 5 Minute Test")
    print("=" * 70)
    print()
    
    print(f"Connecting to {MAC_ADDRESS}...")
    
    try:
        async with BleakClient(MAC_ADDRESS, timeout=20.0, address_type="public") as client:
            print("✓ Connected!")
            print()
            print("Monitoring battery every 30 seconds for 5 minutes...")
            print("(Press Ctrl+C to stop)")
            print()
            
            readings = []
            
            for i in range(10):  # 10 readings over 5 minutes
                try:
                    value = await client.read_gatt_char(CHAR_BATTERY)
                    
                    if len(value) > BATTERY_BYTE_OFFSET:
                        battery = value[BATTERY_BYTE_OFFSET]
                        timestamp = datetime.now().strftime('%H:%M:%S')
                        
                        readings.append((timestamp, battery))
                        print(f"[{timestamp}] Battery: {battery}%")
                    
                    if i < 9:  # Don't sleep after last reading
                        await asyncio.sleep(30)
                        
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Read error: {e}")
            
            # Summary
            print()
            print("=" * 70)
            print("MONITORING SUMMARY")
            print("=" * 70)
            
            if readings:
                batteries = [r[1] for r in readings]
                print(f"Readings: {len(readings)}")
                print(f"Min: {min(batteries)}%")
                print(f"Max: {max(batteries)}%")
                print(f"Average: {sum(batteries)/len(batteries):.1f}%")
                print(f"Change: {batteries[-1] - batteries[0]}%")
            
            print("=" * 70)
            print()
            
    except Exception as e:
        print(f"\n❌ Connection error: {e}\n")
        return False


async def main():
    """Main entry point."""
    
    monitor_mode = "--monitor" in sys.argv
    
    if monitor_mode:
        await monitor_battery()
    else:
        await read_battery_once()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nStopped by user\n")
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        sys.exit(1)
