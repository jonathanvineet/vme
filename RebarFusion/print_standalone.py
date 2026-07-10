import json
with open('debug/phase09/SS-GF-01(M).dxf/standalone.json') as f:
    objects = json.load(f)
import collections
reasons = collections.Counter(o['rejection_reason'] for o in objects)
print('Rejection reasons:', dict(reasons))
for o in objects:
    if o['rejection_reason'] == 'Isolated':
        print(f"Isolated: comp={o['component_uuid'][:8]} geom_type={o.get('recognition_type', 'unknown')} len={o.get('length', 0):.0f} layer={o.get('layer', 'unknown')}")
