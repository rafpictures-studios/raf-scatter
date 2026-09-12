"""
utils/icons.py — Custom icon loader (preview collection).

Placeholder for future custom icon swapping (guide section 2, "Heavy
Customization Ready"). Not used anywhere yet; ui/panels.py currently
relies entirely on built-in Blender icons, already verified against the
icon enum (guide Rule E).

IMPORTANT: once this file is actually used, never pass a custom icon
path as an 'icon=...' string directly — that argument only accepts the
built-in icon enum. Custom icons must go through
pcoll["icon_name"].icon_id via template_icon / layout.label(icon_value=...).
"""

import bpy.utils.previews

_icon_collections = {}


def register():
    pcoll = bpy.utils.previews.new()
    # TODO: load actual .png/.svg icons from resources/icons/, e.g.:
    # icons_dir = os.path.join(os.path.dirname(__file__), "..", "resources", "icons")
    # pcoll.load("my_icon", os.path.join(icons_dir, "my_icon.png"), 'IMAGE')
    _icon_collections["main"] = pcoll


def unregister():
    for pcoll in _icon_collections.values():
        bpy.utils.previews.remove(pcoll)
    _icon_collections.clear()


def get_icon_id(name):
    """Return the icon_id int for use in layout.label(icon_value=...).
    Returns None if the icon hasn't been loaded (no custom icons exist
    yet at this point)."""
    pcoll = _icon_collections.get("main")
    if pcoll is None or name not in pcoll:
        return None
    return pcoll[name].icon_id
