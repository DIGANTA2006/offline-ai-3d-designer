import sys
sys.path.insert(0, '..\src')
from ai3d_designer.core.nlp.parser import RuleBasedParser
import re

parser = RuleBasedParser()

# Test cases
test_cases = [
    'invalid gibberish text',
    '40x20x10 box',
    '50 x 30 x 20 box',
    '10 by 20 by 30',
    'cylinder radius 10 height 50',
    'sphere radius 15',
    'box with 5mm hole',
]

for text in test_cases:
    print(f"\n=== Testing: '{text}' ===")
    result = parser.parse(text)
    if result.success:
        print(f"Success: {result.spec.name}")
        print(f"Features: {len(result.spec.features)}")
        for f in result.spec.features:
            print(f"  Type: {f.type.value}, Params: {list(f.parameters.keys())}")
    else:
        print(f"Failed: {result.error}")
