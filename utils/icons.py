"""Custom icon loader for RAF Scatter preview collections."""
import os

import bpy
import bpy.utils.previews


#----ICON CONFIGURATION----
_SUPPORTED_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
)
_GEOM_RANGE = 255
_GEOM_PADDING = 0.06
_GEOM_MIN_ALPHA = 8
_GEOM_COLOR_STEP = 8
# same header as Blender's own datafiles/icons/*.dat: magic, version 0, 255 x 255 range
_GEOM_HEADER = b"VCO\x00" + bytes((_GEOM_RANGE, _GEOM_RANGE, 0, 0))
_TOOLBAR_ICON_SUBDIR = "raf_scatter/toolbar_icons"
_icon_collections = {}
_biome_preview_keys = {}
_toolbar_icon_handles = {}
_icons_dir = ""


#----LOADING HELPERS----
def _load_menu_icons(pcoll, icons_dir):
    """Load supported menu icons from the icons directory."""
    if not os.path.isdir(icons_dir):
        return
    for filename in sorted(os.listdir(icons_dir)):
        base, extension = os.path.splitext(filename)
        if extension.lower() not in _SUPPORTED_EXTENSIONS:
            continue
        if base in pcoll:
            continue
        pcoll.load(base, os.path.join(icons_dir, filename), "IMAGE")


#----ICON ACCESS----
def get_menu_icon_id(name):
    """Return a menu icon_id, or None when unavailable."""
    pcoll = _icon_collections.get("menu")
    if pcoll is None or name is None or name not in pcoll:
        return None
    return pcoll[name].icon_id


def get_menu_icon_preview(name):
    """Return a menu icon preview for custom GPU drawing."""
    pcoll = _icon_collections.get("menu")
    if pcoll is None or name is None or name not in pcoll:
        return None
    return pcoll[name]


#----TOOLBAR ICONS----
def _pixel_rows(preview):
    """Yield (y, [(r, g, b, a) bytes per pixel]) rows of a preview image, bottom row first."""
    width, height = preview.image_size
    pixels = preview.image_pixels_float
    for y in range(height):
        row = []
        for x in range(width):
            index = (y * width + x) * 4
            row.append(tuple(
                min(255, int(pixels[index + channel] * 255.0 + 0.5)) for channel in range(4)
            ))
        yield y, row


def _quantize(color):
    return tuple(min(255, (value // _GEOM_COLOR_STEP) * _GEOM_COLOR_STEP) for value in color)


def _triangle_data(preview):
    """Return (coords, colors) bytes of a preview image as coloured triangles in 0-255 space."""
    width, height = preview.image_size
    coords = bytearray()
    colors = bytearray()
    offset = _GEOM_RANGE * _GEOM_PADDING
    span = _GEOM_RANGE - 2.0 * offset
    for y, row in _pixel_rows(preview):
        y0 = round(offset + y * span / height)
        y1 = round(offset + (y + 1) * span / height)
        x = 0
        while x < width:
            color = _quantize(row[x])
            if row[x][3] < _GEOM_MIN_ALPHA:
                x += 1
                continue
            run = 1
            while x + run < width and row[x + run][3] >= _GEOM_MIN_ALPHA and _quantize(
                row[x + run]
            ) == color:
                run += 1
            x0 = round(offset + x * span / width)
            x1 = round(offset + (x + run) * span / width)
            coords += bytes((x0, y0, x1, y0, x1, y1, x0, y0, x1, y1, x0, y1))
            colors += bytes(color) * 6
            x += run
    return bytes(coords), bytes(colors)


def get_toolbar_icon_handle(name):
    """Return a native tool icon handle (a .dat path without extension) built from a PNG."""
    if name in _toolbar_icon_handles:
        return _toolbar_icon_handles[name]
    source = os.path.join(_icons_dir, name + ".png")
    preview = get_menu_icon_preview(name)
    if preview is None or not os.path.isfile(source):
        return None
    folder = bpy.utils.user_resource('DATAFILES', path=_TOOLBAR_ICON_SUBDIR, create=True)
    handle = os.path.join(folder, name)
    coords, colors = _triangle_data(preview)
    if not coords:
        return None
    # rewritten once per Blender session so an edited PNG is always picked up
    with open(handle + ".dat", "wb") as handle_file:
        handle_file.write(_GEOM_HEADER + coords + colors)
    _toolbar_icon_handles[name] = handle
    return handle


def get_builtin_icon_value(name):
    """Return the icon_value of a built-in icon name, for widgets that only take icon_value."""
    items = bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items
    return items[name].value if name in items else 0


#----BIOME PREVIEWS----
def reload_biome_previews(biomes):
    """Point each biome at the preview of its thumbnail, loading only new or changed files."""
    pcoll = _icon_collections.get("biomes")
    if pcoll is None:
        return
    _biome_preview_keys.clear()
    for key, thumbnail_path in biomes:
        if thumbnail_path is None or not os.path.isfile(thumbnail_path):
            continue
        # a changed file gets a new preview: freeing one the UI still draws corrupts memory
        preview_key = f"{os.path.normcase(thumbnail_path)}|{os.path.getmtime(thumbnail_path)}"
        if preview_key not in pcoll:
            pcoll.load(preview_key, thumbnail_path, "IMAGE")
        _biome_preview_keys[key] = preview_key


def get_biome_icon_id(key):
    """Return the thumbnail icon_id of a biome, or None when it has no thumbnail."""
    pcoll = _icon_collections.get("biomes")
    preview_key = _biome_preview_keys.get(key)
    if pcoll is None or preview_key not in pcoll:
        return None
    return pcoll[preview_key].icon_id


#----REGISTRATION----
def register():
    """Create preview collections and load custom icons."""
    global _icons_dir
    resources_dir = os.path.join(os.path.dirname(__file__), "..", "resources")
    _icons_dir = os.path.normpath(os.path.join(resources_dir, "icons"))
    menu_collection = bpy.utils.previews.new()
    _load_menu_icons(menu_collection, _icons_dir)
    _icon_collections["menu"] = menu_collection
    _icon_collections["biomes"] = bpy.utils.previews.new()


def unregister():
    """Remove all custom icon preview collections."""
    for pcoll in _icon_collections.values():
        bpy.utils.previews.remove(pcoll)
    _icon_collections.clear()
    _biome_preview_keys.clear()
    _toolbar_icon_handles.clear()