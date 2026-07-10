from typing import List, Tuple

def _select_spacing_sequence(candidates, spacing):
    if spacing <= 0:
        return [item for item in candidates if abs(item[0]) <= 6000.0]

    tolerance = max(25.0, spacing * 0.35)
    
    sorted_candidates = sorted(candidates, key=lambda x: abs(x[0]))
    accepted_offsets = [0.0]
    selected = []
    
    for item in sorted_candidates:
        offset = item[0]
        
        if offset == 0.0:
            selected.append(item)
            continue
            
        nearest_accepted = min(accepted_offsets, key=lambda a: abs(offset - a))
        diff = abs(offset - nearest_accepted)
        
        multiple = diff / spacing
        remainder = abs(multiple - round(multiple))
        
        if remainder * spacing < tolerance:
            selected.append(item)
            accepted_offsets.append(offset)
            
    return selected

# Simulated candidate offsets with 195mm spacing (nominal 200mm)
# and one gap
offsets = [0.0]
for i in range(1, 30):
    if i == 15:
        continue # gap
    offsets.append(i * 195.5)

candidates = [(off, None, 1.0) for off in offsets]
selected = _select_spacing_sequence(candidates, 200.0)
print(f"Selected: {len(selected)} out of {len(candidates)}")
print(f"Last offset selected: {selected[-1][0]}")

