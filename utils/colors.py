"""Colour tags of scatter systems: a distinct random colour per system of a ground."""
import colorsys
import random


_PALETTE_SIZE = 12
_SATURATION = 0.6
_VALUE = 0.9
_SAME_COLOR_DISTANCE = 0.12
PALETTE = tuple(
    colorsys.hsv_to_rgb(index / _PALETTE_SIZE, _SATURATION, _VALUE)
    for index in range(_PALETTE_SIZE)
)


def _distance(color_a, color_b):
    return sum((a - b) ** 2 for a, b in zip(color_a, color_b)) ** 0.5


def pick_color(used_colors):
    """A random palette colour unlike every used one; once all are taken, the least used one."""
    used = [tuple(color) for color in used_colors]
    free = [
        color for color in PALETTE
        if all(_distance(color, other) > _SAME_COLOR_DISTANCE for other in used)
    ]
    if free:
        return random.choice(free)
    counts = [
        sum(1 for other in used if _distance(color, other) <= _SAME_COLOR_DISTANCE)
        for color in PALETTE
    ]
    fewest = min(counts)
    return random.choice([color for color, count in zip(PALETTE, counts) if count == fewest])


def assign_system_color(ground, system):
    """Give a system a colour no other system of its ground has."""
    used = [other.color for other in ground.scatter_systems if other != system and other.has_color]
    system.color = pick_color(used)
    system.has_color = True


def assign_missing_colors(scene):
    """Colour the systems of files saved before colour tags existed."""
    for ground in scene.scatter_grounds:
        for system in ground.scatter_systems:
            if not system.has_color:
                assign_system_color(ground, system)
