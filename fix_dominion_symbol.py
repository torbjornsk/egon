"""
Fix symbol name for Dominion Markets
Changes XAUUSD to XAUUSD.p in all bot files
"""

import json
from pathlib import Path

print("\n" + "="*60)
print("FIXING SYMBOL FOR DOMINION MARKETS")
print("="*60)

# Files to update
files_to_check = [
    'live_trading_bot.py',
    'live_trading_bot_trend.py',
    'bot_gui.py',
    'bot_gui_v3.py',
    'src/bot.py',
    'src/strategies/scalping.py',
    'src/strategies/improved_scalping.py',
    'src/strategies/trend_following.py',
]

old_symbol = "'XAUUSD'"
new_symbol = "'XAUUSD.p'"

updated_files = []

for file_path in files_to_check:
    path = Path(file_path)
    
    if not path.exists():
        continue
    
    # Read file
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if needs update
    if old_symbol in content:
        # Update
        new_content = content.replace(old_symbol, new_symbol)
        
        # Write back
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        updated_files.append(file_path)
        print(f"✓ Updated: {file_path}")

if updated_files:
    print(f"\n✓ Updated {len(updated_files)} files")
    print("\nFiles updated:")
    for f in updated_files:
        print(f"  - {f}")
else:
    print("\n✓ No files needed updating (already using correct symbol)")

print("\n" + "="*60)
print("SYMBOL FIX COMPLETE")
print("="*60)
print("\nYour bots will now use 'XAUUSD.p' for Dominion Markets")
print("\nNext steps:")
print("1. Restart any running bots")
print("2. Run: python tests/test_mt5_connection.py")
print("3. Verify all tests pass")
