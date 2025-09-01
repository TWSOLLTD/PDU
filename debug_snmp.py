#!/usr/bin/env python3
"""
Debug script to test SNMP queries and see raw values
"""

from easysnmp import Session
from config import PDUS, SNMP_TIMEOUT, SNMP_RETRIES

# OIDs to test
L1_PHASE_CURRENT_OID = "1.3.6.1.4.1.318.1.1.12.2.3.1.1.2.1"  # L1 phase current in 0.1A units
L2_PHASE_CURRENT_OID = "1.3.6.1.4.1.318.1.1.12.2.3.1.1.1.1"  # L2 phase current in 0.1A units
L3_PHASE_CURRENT_OID = "1.3.6.1.4.1.318.1.1.12.2.3.1.1.3.1"  # L3 phase current in 0.1A units

FALLBACK_POWER_OIDS = [
    "1.3.6.1.4.1.318.1.1.12.1.16.0",  # Total PDU power in watts
    "1.3.6.1.4.1.318.1.1.4.4.2.1.4.0",  # Total PDU power
]

def test_snmp_queries():
    """Test SNMP queries on all PDUs"""
    print("🔌 PDU Power Monitoring - SNMP Debug Test")
    print("=" * 60)
    print(f"Expected limits for 16A circuit at 240V:")
    print(f"  Max Current: 16.0A")
    print(f"  Max Power: {16 * 240 * 0.95:.1f}W (~3.6kW)")
    print("=" * 60)
    
    for pdu_key, pdu_config in PDUS.items():
        print(f"\n{'='*60}")
        print(f"Testing PDU: {pdu_config['name']} ({pdu_config['ip']})")
        print(f"{'='*60}")
        
        try:
            # Try SNMPv2c
            session = Session(
                hostname=pdu_config['ip'],
                version=2,
                community='public',
                timeout=SNMP_TIMEOUT,
                retries=SNMP_RETRIES
            )
            
            print("\n--- Current OIDs (should be in 0.1A units) ---")
            current_oids = [
                ("L1 Phase Current", L1_PHASE_CURRENT_OID),
                ("L2 Phase Current", L2_PHASE_CURRENT_OID),
                ("L3 Phase Current", L3_PHASE_CURRENT_OID),
            ]
            
            for name, oid in current_oids:
                try:
                    result = session.get(oid)
                    if result and result.value:
                        raw_value = int(result.value)
                        current_amps = raw_value / 10.0
                        power_watts = current_amps * 240 * 0.95  # 240V, 0.95 PF
                        max_power_16a = 16 * 240 * 0.95  # ~3,648W for 16A at 240V
                        
                        # Check if reading exceeds 16A limit
                        status = "✅ OK" if current_amps <= 16 else "🚨 EXCEEDS 16A LIMIT"
                        if current_amps > 16:
                            status += f" (should be max {max_power_16a:.1f}W)"
                        
                        print(f"{name}: Raw={raw_value}, Current={current_amps:.1f}A, Power={power_watts:.1f}W {status}")
                    else:
                        print(f"{name}: No data")
                except Exception as e:
                    print(f"{name}: Error - {str(e)}")
            
            print("\n--- Power OIDs (should be in watts) ---")
            for i, oid in enumerate(FALLBACK_POWER_OIDS):
                try:
                    result = session.get(oid)
                    if result and result.value:
                        raw_value = int(result.value)
                        max_power_16a = 16 * 240 * 0.95  # ~3,648W for 16A at 240V
                        
                        # Check if reading exceeds 16A limit
                        status = "✅ OK" if raw_value <= max_power_16a else "🚨 EXCEEDS 16A LIMIT"
                        if raw_value > max_power_16a:
                            status += f" (should be max {max_power_16a:.1f}W)"
                        
                        print(f"Power OID {i+1}: Raw={raw_value}, Power={raw_value}W {status}")
                    else:
                        print(f"Power OID {i+1}: No data")
                except Exception as e:
                    print(f"Power OID {i+1}: Error - {str(e)}")
                    
        except Exception as e:
            print(f"Failed to connect to {pdu_config['name']}: {str(e)}")

if __name__ == "__main__":
    test_snmp_queries()
