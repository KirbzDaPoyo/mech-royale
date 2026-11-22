"""Local obstacle queries against arena prism footprints."""
import json
import math
from collections import defaultdict
from pathlib import Path


class Arena:
    def __init__(self, directory, step_up):
        world = json.loads((Path(directory) / "v2" / "world.json").read_text())
        self.bounds = world["bounds"]
        self.step_up = step_up
        self.cells = defaultdict(list)
        for prism in world["prisms"]:
            rings = [prism["ring"], *prism["holes"]]
            loops = []
            for ring in rings:
                points = list(zip(ring[::2], ring[1::2]))
                loops.append(list(zip(points, points[1:] + points[:1])))
            xs, ys = rings[0][::2], rings[0][1::2]
            for i in range(math.floor(min(xs) / 16), math.floor(max(xs) / 16) + 1):
                for j in range(math.floor(min(ys) / 16), math.floor(max(ys) / 16) + 1):
                    self.cells[i, j].append((prism["base"], prism["top"], loops))

    def clear(self, x, y, z, radius, height):
        b = self.bounds
        if not (b["minX"] + radius <= x <= b["maxX"] - radius and
                b["minY"] + radius <= y <= b["maxY"] - radius):
            return False
        # Query all bins touched by the mech, including adjacent bins near an edge.
        seen = set()
        for i in range(math.floor((x-radius)/16), math.floor((x+radius)/16)+1):
            for j in range(math.floor((y-radius)/16), math.floor((y+radius)/16)+1):
                for base, top, loops in self.cells.get((i, j), ()):
                    if id(loops) in seen or top <= z + self.step_up or base >= z + height:
                        continue
                    seen.add(id(loops))
                    inside = False
                    for edges in loops:
                        for (ax, ay), (bx, by) in edges:
                            dx, dy = bx-ax, by-ay
                            if (ay > y) != (by > y) and x < ax + dx*(y-ay)/dy:
                                inside = not inside
                            if (min(ax,bx)-radius <= x <= max(ax,bx)+radius and
                                    min(ay,by)-radius <= y <= max(ay,by)+radius):
                                length_sq = dx*dx + dy*dy
                                t = min(1, max(0, ((x-ax)*dx+(y-ay)*dy)/length_sq)) if length_sq else 0
                                if (x-ax-t*dx)**2 + (y-ay-t*dy)**2 <= radius**2:
                                    return False
                    if inside:
                        return False
        return True

    def nearby_cover(self, x, y, z, stats, opponent):
        # Sample the sightline near the proposed destination, using the top of
        # our mech so a low wall cannot qualify as full-body cover.
        ox, oy, oz = opponent
        distance = math.hypot(ox - x, oy - y)
        for offset in (4, 8, 12, 18, 24):
            if offset >= distance:
                break
            t = offset / distance
            sample_z = (1 - t) * (z + stats["height"]) + t * (oz + 7)
            if not self.clear(x + t * (ox - x), y + t * (oy - y), sample_z, 0, 0.01):
                return True
        return False
