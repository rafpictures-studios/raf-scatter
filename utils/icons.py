"""
utils/icons.py — Custom icon loader (preview collection).

Loads effector, scatter-system, and brush thumbnail PNGs from
resources/thumbnails/ into a preview collection, exposed via
get_icon_id(name) for use with icon_value=... in UI draw calls.
"""

import os
import bpy.utils.previews

_icon_collections = {}

_THUMBNAIL_NAMES = (
    "texture_mask",
    "proximity_mask",
    "position_mask",
    "slope_mask",
    "vertex_mask",
    "manual_scatter",
    "procedural_scatter",
    "brush_line",
    "brush_density",
    "brush_delete",
    "brush_slide",
)


def register():
    pcoll = bpy.utils.previews.new()

    thumbnails_dir = os.path.join(os.path.dirname(__file__), "..", "resources", "thumbnails")
    missing = []
    for name in _THUMBNAIL_NAMES:
        filepath = os.path.join(thumbnails_dir, f"{name}.png")
        if os.path.isfile(filepath):
            pcoll.load(name, filepath, 'IMAGE')
        else:
            missing.append(filepath)

    if missing:
        print("[RAF Scatter] Thumbnail file(s) not found, falling back to built-in icons:")
        for path in missing:
            print(f"  - {path}")

    _icon_collections["main"] = pcoll


def unregister():
    for pcoll in _icon_collections.values():
        bpy.utils.previews.remove(pcoll)
    _icon_collections.clear()


def get_icon_id(name):
    """Return the icon_id int for use with icon_value=... in UI draw
    calls. Returns None if the thumbnail wasn't loaded (missing file)."""
    pcoll = _icon_collections.get("main")
    if pcoll is None or name not in pcoll:
        return None
    return pcoll[name].icon_id