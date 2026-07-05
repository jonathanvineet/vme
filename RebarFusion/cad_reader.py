"""
===========================================================
cad_reader.py

Reads

- DWG (Aspose.CAD)
- DXF (ezdxf)
- Vector PDF (PyMuPDF)

Everything is converted into one common entity format.

===========================================================
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
import math


@dataclass
class Entity:

    entity_type: str

    layer: str

    start: Optional[Tuple[float, float]] = None

    end: Optional[Tuple[float, float]] = None

    points: Optional[List[Tuple[float, float]]] = None

    center: Optional[Tuple[float, float]] = None

    radius: Optional[float] = None

    text: Optional[str] = None


class CADReader:

    def __init__(self, filename):

        self.filename = filename

        self.extension = Path(filename).suffix.lower()

    def read(self):

        if self.extension == ".dwg":
            entities = self._read_dwg()

        elif self.extension == ".dxf":
            entities = self._read_dxf()

        elif self.extension == ".pdf":
            entities = self._read_pdf()

        else:
            raise Exception("Unsupported file.")

        # report layer usage for any input type
        layers = {}
        for e in entities:
            layers[e.layer] = layers.get(e.layer, 0) + 1

        print("\nLayers found:")
        for k, v in sorted(layers.items()):
            print(k, v)

        return entities

    ##################################################################
    # DXF
    ##################################################################

    def _read_dxf(self):

        import ezdxf

        doc = ezdxf.readfile(self.filename)

        msp = doc.modelspace()

        entities = []

        for e in msp:

            layer = e.dxf.layer

            if e.dxftype() == "LINE":

                entities.append(

                    Entity(

                        entity_type="LINE",

                        layer=layer,

                        start=(e.dxf.start.x, e.dxf.start.y),

                        end=(e.dxf.end.x, e.dxf.end.y)

                    )

                )

            elif e.dxftype() == "LWPOLYLINE":

                pts = [(p[0], p[1]) for p in e]

                entities.append(

                    Entity(

                        entity_type="LWPOLYLINE",

                        layer=layer,

                        points=pts

                    )

                )

            elif e.dxftype() == "POLYLINE":

                pts = []

                for v in e.vertices:

                    pts.append((v.dxf.location.x, v.dxf.location.y))

                entities.append(

                    Entity(

                        entity_type="POLYLINE",

                        layer=layer,

                        points=pts

                    )

                )

            elif e.dxftype() == "ARC":

                entities.append(

                    Entity(

                        entity_type="ARC",

                        layer=layer,

                        center=(e.dxf.center.x, e.dxf.center.y),

                        radius=e.dxf.radius

                    )

                )

            elif e.dxftype() in ["TEXT", "MTEXT"]:

                try:
                    txt = e.plain_text()
                except:
                    txt = e.dxf.text

                entities.append(

                    Entity(

                        entity_type="TEXT",

                        layer=layer,

                        text=txt

                    )

                )

        return entities

        # report layer usage
        layers = {}

        for e in entities:
            layers[e.layer] = layers.get(e.layer, 0) + 1

        print("\nLayers found:")

        for k, v in sorted(layers.items()):
            print(k, v)

    ##################################################################
    # DWG
    ##################################################################

    def _read_dwg(self):

        from aspose.cad import Image
        from aspose.cad.fileformats.cad import CadImage

        img = Image.load(self.filename)

        cad = img if isinstance(img, CadImage) else CadImage(img)

        entities = []

        # -------- ModelSpace --------

        blocks = cad.block_entities

        model = None

        for block in blocks.values:

            if block.name.lower() == "model_space":

                model = block

                break

        if model is None:
            raise Exception("Model_Space not found.")

        for e in model.entities:

            layer = getattr(e, "layer_name", "")

            name = e.__class__.__name__.upper()

            ###########################################################

            if "LINE" in name:

                try:

                    start = (e.first_point.x, e.first_point.y)

                    end = (e.second_point.x, e.second_point.y)

                    entities.append(

                        Entity(

                            entity_type="LINE",

                            layer=layer,

                            start=start,

                            end=end

                        )

                    )

                except:
                    pass

            ###########################################################

            elif "LWPOLYLINE" in name or "POLYLINE" in name:

                try:

                    pts = []

                    for p in e.polyline_points:

                        pts.append((p.x, p.y))

                    entities.append(

                        Entity(

                            entity_type="POLYLINE",

                            layer=layer,

                            points=pts

                        )

                    )

                except:
                    pass

            ###########################################################

            elif "ARC" in name:

                try:

                    entities.append(

                        Entity(

                            entity_type="ARC",

                            layer=layer,

                            center=(e.center_point.x,
                                    e.center_point.y),

                            radius=e.radius

                        )

                    )

                except:
                    pass

            ###########################################################

            elif "TEXT" in name:

                try:

                    entities.append(

                        Entity(

                            entity_type="TEXT",

                            layer=layer,

                            text=e.default_value

                        )

                    )

                except:
                    pass

        return entities

    ##################################################################
    # VECTOR PDF
    ##################################################################

    def _read_pdf(self):

        import fitz

        entities = []

        doc = fitz.open(self.filename)

        for page in doc:

            drawings = page.get_drawings()

            for d in drawings:

                for item in d["items"]:

                    code = item[0]

                    ##################################################

                    if code == "l":

                        p1 = item[1]

                        p2 = item[2]

                        entities.append(

                            Entity(

                                entity_type="LINE",

                                layer="PDF",

                                start=(p1.x, p1.y),

                                end=(p2.x, p2.y)

                            )

                        )

                    ##################################################

                    elif code == "re":

                        r = item[1]

                        pts = [

                            (r.x0, r.y0),

                            (r.x1, r.y0),

                            (r.x1, r.y1),

                            (r.x0, r.y1),

                            (r.x0, r.y0)

                        ]

                        entities.append(

                            Entity(

                                entity_type="POLYLINE",

                                layer="PDF",

                                points=pts

                            )

                        )

            words = page.get_text("words")

            for w in words:

                entities.append(

                    Entity(

                        entity_type="TEXT",

                        layer="PDF",

                        text=w[4]

                    )

                )

        return entities