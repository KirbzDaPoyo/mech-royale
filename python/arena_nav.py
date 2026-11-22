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
        self.roofs = []
        for prism in world["prisms"]:
            rings = [prism["ring"], *prism["holes"]]
            loops = []
            for ring in rings:
                points = list(zip(ring[::2], ring[1::2]))
                loops.append(list(zip(points, points[1:] + points[:1])))
            if prism["kind"] == "building" and not prism["holes"]:
                edges = loops[0]
                winding = 1 if sum(ax*by - ay*bx for (ax, ay), (bx, by) in edges) > 0 else -1
                for (ax, ay), (bx, by) in edges:
                    length = math.hypot(bx-ax, by-ay)
                    if length < 15:
                        continue
                    nx, ny = winding * (ay-by)/length, winding * (bx-ax)/length
                    mx, my = (ax+bx)/2, (ay+by)/2
                    launch = (mx - 6*nx, my - 6*ny)
                    landing = (mx + 6*nx, my + 6*ny)
                    lx, ly = landing
                    crossings = sum((y1 > ly) != (y2 > ly) and lx < x1 + (x2-x1)*(ly-y1)/(y2-y1)
                                    for (x1,y1), (x2,y2) in edges)
                    if crossings % 2:
                        self.roofs.append((launch, landing, prism["top"]))
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

    def choose_roof(self, me, zone):
        x, y, z = me["pos"]
        stats = me["stats"]
        radius, height = stats["radius"], stats["height"]
        # Leave energy for the crossing and for recovering from an interrupted climb.
        climb = min(32, (me["energy"] - 25) * stats["max_rise_speed"] / stats["jet_drain"])
        best_distance = 45
        best = None
        for launch, landing, top in self.roofs:
            distance = math.dist((x, y), launch)
            if distance >= best_distance or not 8 <= top - z <= climb:
                continue
            if any(math.dist(point, zone["next_center"]) > zone["next_radius"] - 12
                   for point in (launch, landing)):
                continue
            if not self.clear(*landing, top, radius, height):
                continue
            steps = max(1, math.ceil(distance / 3))
            if all(self.clear(x + (launch[0]-x)*i/steps, y + (launch[1]-y)*i/steps,
                              z, radius, height) for i in range(1, steps + 1)):
                best_distance = distance
                best = (launch, landing, top)
        return best
