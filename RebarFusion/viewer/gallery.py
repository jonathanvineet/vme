import os
import random
import matplotlib.pyplot as plt
from core.geometry.repository import DrawingRepository
from core.geometry.entities import (
    LineEntity, ArcEntity, PolylineEntity, InsertEntity, 
    TextEntity, MTextEntity, DimensionEntity, HatchEntity, CircleEntity
)

def _plot_entity(ax, entity):
    if isinstance(entity, LineEntity):
        ax.plot([entity.start.x, entity.end.x], [entity.start.y, entity.end.y], 'b-', linewidth=1)
    elif isinstance(entity, PolylineEntity):
        xs = [p.x for p in entity.vertices]
        ys = [p.y for p in entity.vertices]
        if entity.is_closed and len(xs) > 0:
            xs.append(xs[0])
            ys.append(ys[0])
        ax.plot(xs, ys, 'g-', linewidth=1)
    elif isinstance(entity, CircleEntity):
        circle = plt.Circle((entity.center.x, entity.center.y), entity.radius, color='r', fill=False)
        ax.add_patch(circle)
    # For others, we just plot their bounding box or insertion point for context in a gallery crop
    elif isinstance(entity, (TextEntity, MTextEntity)):
        ax.plot(entity.insertion_point.x, entity.insertion_point.y, 'ko')
        ax.text(entity.insertion_point.x, entity.insertion_point.y, entity.text, fontsize=8)
    elif isinstance(entity, InsertEntity):
        ax.plot(entity.insertion_point.x, entity.insertion_point.y, 'rx')
        ax.text(entity.insertion_point.x, entity.insertion_point.y, entity.block_name, fontsize=8)

def _get_entity_bbox(entity):
    bb = entity.bounding_box
    if bb == (0.0, 0.0, 0.0, 0.0):
        # Fallback to insertion points
        if hasattr(entity, 'start') and hasattr(entity, 'end'):
            return min(entity.start.x, entity.end.x), min(entity.start.y, entity.end.y), max(entity.start.x, entity.end.x), max(entity.start.y, entity.end.y)
        elif hasattr(entity, 'insertion_point'):
            return entity.insertion_point.x-10, entity.insertion_point.y-10, entity.insertion_point.x+10, entity.insertion_point.y+10
        elif hasattr(entity, 'center') and hasattr(entity, 'radius'):
            return entity.center.x - entity.radius, entity.center.y - entity.radius, entity.center.x + entity.radius, entity.center.y + entity.radius
        elif hasattr(entity, 'vertices') and entity.vertices:
            xs = [p.x for p in entity.vertices]
            ys = [p.y for p in entity.vertices]
            return min(xs), min(ys), max(xs), max(ys)
    return bb

def generate_gallery(repo: DrawingRepository, base_dir: str, max_samples: int = 5):
    """Generates image crops for entity samples."""
    gallery_dir = os.path.join(base_dir, "entity_gallery")
    
    entity_lists = {
        "LINE": repo.lines,
        "ARC": repo.arcs,
        "POLYLINE": repo.polylines,
        "INSERT": repo.inserts,
        "TEXT": repo.texts,
        "MTEXT": repo.mtexts,
        "DIMENSION": repo.dimensions,
        "HATCH": repo.hatches,
        "CIRCLE": repo.circles
    }
    
    for etype, entities in entity_lists.items():
        if not entities:
            continue
            
        type_dir = os.path.join(gallery_dir, etype)
        os.makedirs(type_dir, exist_ok=True)
        
        # Pick random samples
        samples = random.sample(entities, min(max_samples, len(entities)))
        
        for i, entity in enumerate(samples):
            fig, ax = plt.subplots(figsize=(4, 4))
            
            _plot_entity(ax, entity)
            
            bbox = _get_entity_bbox(entity)
            if bbox != (0.0, 0.0, 0.0, 0.0):
                # Add padding
                w = max(bbox[2] - bbox[0], 1.0)
                h = max(bbox[3] - bbox[1], 1.0)
                pad_x = w * 0.2
                pad_y = h * 0.2
                ax.set_xlim(bbox[0] - pad_x, bbox[2] + pad_x)
                ax.set_ylim(bbox[1] - pad_y, bbox[3] + pad_y)
            else:
                ax.set_xlim(-100, 100)
                ax.set_ylim(-100, 100)
                
            ax.set_aspect('equal', adjustable='datalim')
            ax.set_title(f"{etype} {entity.id.hex[:8]}\nLyr: {entity.layer}", fontsize=8)
            
            out_path = os.path.join(type_dir, f"sample_{i+1:03d}.png")
            plt.savefig(out_path, dpi=100, bbox_inches='tight')
            plt.close(fig)
