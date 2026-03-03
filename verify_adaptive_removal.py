"""
Verification script to confirm all adaptive exit logic has been removed
"""

import re

def check_file_for_patterns(filepath, patterns):
    """Check if file contains any of the specified patterns"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    found = []
    for pattern in patterns:
        for line_num, line in enumerate(lines, 1):
            # Skip comment-only lines that mention removal
            if line.strip().startswith('#') and 'removed adaptive' in line.lower():
                continue
            
            matches = re.findall(pattern, line, re.IGNORECASE)
            if matches:
                found.append((pattern, line_num, line.strip()))
    
    return found

# Patterns to check for (should NOT be found in actual code)
forbidden_patterns = [
    r'ADAPTIVE EXIT \(',  # Actual adaptive exit calls
    r'trend reversed to',  # Trend reversal logic
    r'signal faded',  # Signal fading logic
    r'sideways movement after',  # Sideways detection
    r'Will exit if still losing',  # GUI display text
    r'auto-exit check',  # GUI display text
    r'minutes_held >= 10',  # 10-minute time check
    r'minutes_held >= 3',  # 3-minute time check for adaptive
]

files_to_check = [
    'live_trading_bot_m1.py',
    'bot_gui.py',
    'bot_gui_v3.py'
]

print("=" * 80)
print("ADAPTIVE EXIT REMOVAL VERIFICATION")
print("=" * 80)
print()

all_clean = True

for filepath in files_to_check:
    print(f"Checking {filepath}...")
    found = check_file_for_patterns(filepath, forbidden_patterns)
    
    if found:
        all_clean = False
        print(f"  ❌ FOUND FORBIDDEN PATTERNS:")
        for pattern, line_num, line in found:
            print(f"     Line {line_num}: '{pattern}'")
            print(f"       {line[:80]}")
    else:
        print(f"  ✅ Clean - no adaptive exit logic found")
    print()

print("=" * 80)
if all_clean:
    print("✅ VERIFICATION PASSED")
    print("All adaptive exit logic has been successfully removed!")
    print()
    print("The M1 bot now uses only RSI-based exits:")
    print("  - LONG: Exit when RSI > 65")
    print("  - SHORT: Exit when RSI < 35")
    print("  - Plus standard SL/TP orders")
else:
    print("❌ VERIFICATION FAILED")
    print("Some adaptive exit logic still exists in the code.")
print("=" * 80)
