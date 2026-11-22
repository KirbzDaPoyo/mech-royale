"""Placement-focused pilot for the Mech Royale arena."""
import math

import mechfight as mf


class Bot:
    name = "Orbit Strider Approach 0.25"

    def __init__(self, hello: mf.Hello):
        self.anchor = None
        self.anchor_time = 0
        self.jet_until = 0
        self.turn = 1 if hello["slot"] % 2 else -1
        self.rules = hello["config"]
        self.drone_range = self.rules["npc"]["aggro_range"]

    def act(self, obs: mf.Observation) -> mf.Action:
        me = obs["self"]
        x, y, z = me["pos"]
        zone = obs["zone"]
        cx, cy = zone["next_center"]
        radius = zone["next_radius"]
        margin = min(28, radius * 0.22)
        distance = math.hypot(cx - x, cy - y)
        threats = []
        for actor in obs["mechs"]:
            if actor["kind"] != "npc":
                continue
            reach = self.drone_range + 12
            ax, ay = actor["pos"][:2]
            if math.hypot(ax - x, ay - y) < reach:
                threats.append((ax, ay, reach))

        gun, secondary = me["weapons"]
        def horizontal(item):
            return math.dist((x, y), item["pos"][:2])

        pickups = [p for p in obs["pickups"] if p["kind"] in ("lightning", "laser")
                   and secondary is None and abs(p["pos"][2] - z) <= 4]
        resources = [item for item in obs["cubes"] if abs(item["pos"][2] - z) <= 4]
        resources.extend(pickups)
        goal = min((item for item in resources if horizontal(item) < 65
                    and math.dist(item["pos"][:2], (cx, cy)) < radius - margin),
                   key=horizontal, default=None)
        # Cross the nearest opponent's line of sight while staying inside both circles.
        opponents = [m for m in obs["mechs"] if m["kind"] == "mech"
                     and horizontal(m) <= gun["stats"]["range"]]
        opponent = min(opponents, key=horizontal, default=None)
        strafe = None
        if opponent:
            ox, oy = opponent["pos"][:2]
            separation = max(1, math.hypot(ox - x, oy - y))
            strafe = (self.turn * (y - oy) / separation, self.turn * (ox - x) / separation)
        must_move = strafe or distance > max(1, radius - margin) or threats or not me["in_zone"] or goal
        move = [0.0, 0.0]
        now = obs["t"]
        if must_move:
            inward = math.atan2(cy - y, cx - x)
            stride = min(14, max(1, distance)) if radius < 15 else 14
            if goal:
                stride = max(1, min(stride, horizontal(goal)))
            best_cost = math.inf
            for i in range(24):
                angle = inward + self.turn * i * math.tau / 24
                dx, dy = math.cos(angle), math.sin(angle)
                px, py = x + stride * dx, y + stride * dy
                future_dist = math.hypot(px - cx, py - cy)
                cost = 3 * max(0, future_dist - radius + margin)
                cost += 6 * max(0, math.dist((px, py), zone["center"]) - zone["radius"])
                if strafe:
                    cost -= 0.25 * stride * (dx * strafe[0] + dy * strafe[1])
                    # Favor closing gently while outside a 30 m orbit.
                    if separation > 30:
                        cost += 0.25 * max(0, math.hypot(px - ox, py - oy) - 30)
                if goal:
                    cost += 0.65 * math.dist((px, py), goal["pos"][:2])
                for ax, ay, reach in threats:
                    cost += max(0, reach - math.hypot(px - ax, py - ay))
                if cost < best_cost:
                    best_cost = cost
                    move = [dx, dy]
            if self.anchor is None:
                self.anchor, self.anchor_time = (x, y), now
            elif now - self.anchor_time >= 1.2:
                if math.dist((x, y), self.anchor) < 3 and me["energy"] > 20:
                    self.jet_until = now + 2.6
                self.anchor, self.anchor_time = (x, y), now
        else:
            self.anchor = None
            self.jet_until = 0

        jet = now < self.jet_until
        action = {"tick": obs["tick"], "move": move, "jump": jet and me["grounded"],
                  "boost": jet or (not me["in_zone"] and me["grounded"] and me["energy"] > 35)}
        nearby = min(pickups, key=horizontal, default=None)
        if nearby and horizontal(nearby) <= self.rules["loot"]["pickup_radius"]:
            action["take"] = nearby["id"]

        gun_stats = gun["stats"]
        max_range = max(gun_stats["range"], secondary["stats"]["range"] if secondary else 0)
        targets = [m for m in obs["mechs"] if horizontal(m) <= max_range
                   and (m["kind"] == "mech" or horizontal(m) < self.drone_range)]
        target = min(targets, key=horizontal, default=None)
        if target is None:
            target = min((c for c in obs["crates"] if horizontal(c) < 120),
                         key=horizontal, default=None)
        if target:
            kind = target.get("kind", "crate")
            heights = {"mech": self.rules["mech"]["height"], "npc": self.rules["npc"]["height"],
                       "crate": self.rules["crates"]["height"]}
            tx, ty, tz = target["pos"]
            dist = math.dist(target["pos"], me["pos"])
            laser = secondary and secondary["kind"] == "laser" and secondary["cooldown"] <= 0
            delay = 0 if laser else dist / gun_stats["speed"]
            vx, vy, vz = target.get("vel", (0, 0, 0))
            dx, dy = tx + vx * delay - x, ty + vy * delay - y
            dz = tz + heights[kind] / 2 + vz * delay - z - me["stats"]["muzzle_height"]
            yaw, pitch = math.atan2(dy, dx), math.atan2(dz, math.hypot(dx, dy))
            action["aim"] = [yaw, pitch]
            aligned = (abs(math.remainder(yaw - me["aim"][0], math.tau)) < 0.12
                       and abs(pitch - me["aim"][1]) < 0.12)
            use_secondary = False
            if laser and dist <= secondary["stats"]["range"]:
                use_secondary = secondary.get("charge", 0) < secondary["stats"]["charge"] or not aligned
            elif secondary and secondary["kind"] == "lightning":
                use_secondary = aligned and dist <= secondary["stats"]["range"]
            action["fire"] = [aligned and dist <= gun_stats["range"], use_secondary]
        else:
            action["aim"] = [math.remainder(now * 0.85 * self.turn, math.tau), 0]
            action["reload"] = gun["ammo"] < gun_stats["mag"] and not gun["reload"]
        if obs["offer"]:
            priorities = ["armor", "plating", "nanites", "servos", "reactor"]
            choices = obs["offer"]["choices"]
            action["pick"] = min(range(len(choices)), key=lambda i:
                priorities.index(choices[i]["id"]) if choices[i]["id"] in priorities else len(priorities))
        return action


if __name__ == "__main__":
    mf.run(Bot)
