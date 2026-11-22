"""Placement-focused pilot for the Mech Royale arena."""
import math

import mechfight as mf


class Bot:
    name = "Quiet Orbit"

    def __init__(self, hello: mf.Hello):
        self.anchor = None
        self.anchor_time = 0
        self.jet_until = 0
        self.turn = 1 if hello["slot"] % 2 else -1
        self.drone_range = hello["config"]["vision"]["near_range"]

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
            reach = 110 if actor["kind"] == "mech" else self.drone_range + 12
            ax, ay = actor["pos"][:2]
            if math.hypot(ax - x, ay - y) < reach:
                threats.append((ax, ay, reach))

        # Stand still when safely inside the upcoming circle and undisturbed.
        # When moving, score short candidate paths against both circles and nearby actors.
        must_move = distance > max(1, radius - margin) or threats or not me["in_zone"]
        move = [0.0, 0.0]
        now = obs["t"]
        if must_move:
            inward = math.atan2(cy - y, cx - x)
            stride = min(14, max(1, distance)) if radius < 15 else 14
            best_cost = math.inf
            for i in range(24):
                angle = inward + self.turn * i * math.tau / 24
                dx, dy = math.cos(angle), math.sin(angle)
                px, py = x + stride * dx, y + stride * dy
                future_dist = math.hypot(px - cx, py - cy)
                cost = 3 * max(0, future_dist - radius + margin)
                cost += 6 * max(0, math.dist((px, py), zone["center"]) - zone["radius"])
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
        enemies = [m for m in obs["mechs"] if m["kind"] == "mech"]
        if enemies:
            enemy = min(enemies, key=lambda m: math.dist(me["pos"], m["pos"]))
            tx, ty, tz = enemy["pos"]
            speed = me["weapons"][0]["stats"]["speed"]
            delay = math.dist(me["pos"], enemy["pos"]) / speed
            dx = tx + enemy["vel"][0] * delay - x
            dy = ty + enemy["vel"][1] * delay - y
            yaw = math.atan2(dy, dx)
            action["aim"] = [yaw, math.atan2(tz + 4.5 - z - me["stats"]["muzzle_height"], math.hypot(dx, dy))]
            aligned = abs(math.remainder(yaw - me["aim"][0], math.tau)) < 0.12
            action["fire"] = [aligned and math.hypot(dx, dy) < 85, False]
        else:
            action["aim"] = [math.remainder(now * 0.85 * self.turn, math.tau), 0]
            gun = me["weapons"][0]
            action["reload"] = gun["ammo"] < gun["stats"]["mag"] and not gun["reload"]
        if obs["offer"]:
            priorities = ["armor", "plating", "nanites", "servos", "reactor"]
            choices = obs["offer"]["choices"]
            action["pick"] = min(range(len(choices)), key=lambda i:
                priorities.index(choices[i]["id"]) if choices[i]["id"] in priorities else len(priorities))
        return action


if __name__ == "__main__":
    mf.run(Bot)
