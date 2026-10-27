from src.ai3d_designer.core.nlp.parser import RuleBasedParser, UnitSystem
import re

parser = RuleBasedParser()
text = 'A tube with 20mm outer diameter, 10mm inner diameter and 50mm length'.lower()

# Manually test the scalar_rules
number = parser._NUMBER
unit = parser._UNIT

scalar_rules = {
    'outer_diameter': [
        rf'(?P<num>{number})\s*(?P<unit>{unit})?\s*(?:outer|outside|external|od)\s*(?:diameter|diam|dia)?\b',
        rf'\b(?:outer|outside|external|od)\s*(?:diameter|diam|dia)?\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?',
        rf'\b(?:od)\s*(?P<num>{number})\s*(?P<unit>{unit})?',
    ],
    'inner_diameter': [
        rf'(?P<num>{number})\s*(?P<unit>{unit})?\s*(?:inner|inside|internal|id)\s*(?:diameter|diam|dia)?\b',
        rf'\b(?:inner|inside|internal|id)\s*(?:diameter|diam|dia)?\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?',
        rf'\b(?:id)\s*(?P<num>{number})\s*(?P<unit>{unit})?',
    ],
    'wall_thickness': [
        rf'(?P<num>{number})\s*(?P<unit>{unit})?\s*wall\s*thickness\b',
        rf'\bwall\s*thickness\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?',
    ],
    'length': [
        rf'\b(?:length|long)\s*(?:of|=|:)?\s*(?P<num>{number})\s*(?P<unit>{unit})?',
        rf'(?P<num>{number})\s*(?P<unit>{unit})?\s*(?:long|length)\b',
    ],
}

for key, patterns in scalar_rules.items():
    for pattern in patterns:
        found = re.search(pattern, text, re.IGNORECASE)
        if found:
            print(f'{key}: matched pattern \"{pattern[:60]}...\" -> {found.groupdict()}')
            break
