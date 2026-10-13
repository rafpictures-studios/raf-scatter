"""Viewport HUD for RAF Scatter manual painting."""
import math
import os
import time

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from . import icons as icon_utils


#----HUD CONSTANTS----
_HUD_HINTS = (
    ("F", "Brush size"),
    ("R", "Distance Min"),
    ("Shift+F", "Brush strength"),
    ("Alt+Shift+W", "Brush pie"),
)
_BRUSH_HINTS = {
    'LINE': ("F", "Shift+F", "Alt+Shift+W"),
    'DENSITY': ("F", "R", "Shift+F", "Alt+Shift+W"),
    'GROW': ("F", "Shift+F", "Alt+Shift+W"),
    'DELETE': ("F", "Alt+Shift+W"),
    'SLIDE': ("F", "Shift+F", "Alt+Shift+W"),
}
_BRUSH_LABELS = {
    'LINE': "Add",
    'DENSITY': "Density",
    'GROW': "Grow",
    'DELETE': "Delete",
    'SLIDE': "Slide",
}
_HUD_FONT_ID = 0
_HUD_FONT_SIZE = 24.0
_HUD_HINT_FONT_SIZE = 17.0
_HUD_LINE_HEIGHT = 26.0
_HUD_HEADER_HEIGHT = 40.0
_HUD_LAST_ROW_HEIGHT = 22.0
_HUD_PAD = 19.0
_HUD_MARGIN_X = 28.0
_HUD_BOTTOM_OFFSET = 60.0
_HUD_ICON_SIZE = 34.0
_HUD_LOGO_MAX_WIDTH = 150.0
_HUD_HEADER_GAP = 10.0
_HUD_KEY_GAP = 20.0
_HUD_DIVIDER_HEIGHT = 1.0
_HUD_DIVIDER_GAP = 9.0
_HUD_HINT_TOP_GAP = 32.0
_HUD_CORNER_RADIUS = 8.0
_HUD_BG_COLOR = (0.0, 0.0, 0.0, 0.70)
_HUD_BRUSH_COLOR = (1.0, 1.0, 1.0, 1.0)
_HUD_KEY_COLOR = (1.0, 1.0, 1.0, 0.85)
_HUD_ACTION_COLOR = (1.0, 1.0, 1.0, 0.60)
_HUD_DIVIDER_COLOR = (1.0, 1.0, 1.0, 0.35)
_LOGO_ICON_KEY = "raf_scatter_logo"
_LOGO_FILE_NAME = "raf_scatter_logo.png"
_LOAD_MAX_ATTEMPTS = 20
_PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PREWARM_FIRST_DELAY = 1.0
_PREWARM_STEP_INTERVAL = 0.05
_PREWARM_RETRY_INTERVAL = 0.5
_PREWARM_MAX_TICKS = 40


#----RUNTIME STATE----
_hud_handle = None
_texture_draw_failed = False
_logo = None
_logo_attempts = 0
_prewarm_ticks = 0
_color_shader = None
_image_shader = None
_box_batch_cache = {}
_image_batch_cache = {}


#----DRAWING HELPERS----
def _get_color_shader():
    global _color_shader
    if _color_shader is None:
        _color_shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    return _color_shader


def _get_image_shader():
    global _image_shader
    if _image_shader is None:
        _image_shader = gpu.shader.from_builtin("IMAGE")
    return _image_shader


def _draw_box(x, y, width, height, color):
    shader = _get_color_shader()
    key = (round(x, 2), round(y, 2), round(width, 2), round(height, 2))
    batch = _box_batch_cache.get(key)
    if batch is None:
        vertices = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
        batch = batch_for_shader(shader, "TRI_FAN", {"pos": vertices})
        _box_batch_cache[key] = batch
    gpu.state.blend_set("ALPHA")
    try:
        shader.uniform_float("color", color)
        batch.draw(shader)
    finally:
        gpu.state.blend_set("NONE")


def _draw_rounded_box(x, y, width, height, radius, color):
    shader = _get_color_shader()
    key = (round(x, 2), round(y, 2), round(width, 2), round(height, 2), round(radius, 2))
    batch = _box_batch_cache.get(key)
    if batch is None:
        corners = (
            (x + width - radius, y + radius, -90.0),
            (x + width - radius, y + height - radius, 0.0),
            (x + radius, y + height - radius, 90.0),
            (x + radius, y + radius, 180.0),
        )
        center = (x + width * 0.5, y + height * 0.5)
        vertices = [center]
        segments = 6
        for cx, cy, start_angle in corners:
            for index in range(segments + 1):
                angle = math.radians(start_angle + 90.0 * index / segments)
                vertices.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        vertices.append(vertices[1])  # TRI_FAN does not close itself
        batch = batch_for_shader(shader, "TRI_FAN", {"pos": vertices})
        _box_batch_cache[key] = batch
    gpu.state.blend_set("ALPHA")
    try:
        shader.uniform_float("color", color)
        batch.draw(shader)
    finally:
        gpu.state.blend_set("NONE")


def _draw_texture(texture, x, y, width, height, tag="texture"):
    global _texture_draw_failed
    if _texture_draw_failed or texture is None:
        return
    shader = _get_image_shader()
    key = (round(x, 2), round(y, 2), round(width, 2), round(height, 2))
    batch = _image_batch_cache.get(key)
    if batch is None:
        vertices = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
        uvs = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
        batch = batch_for_shader(shader, "TRI_FAN", {"pos": vertices, "texCoord": uvs})
        _image_batch_cache[key] = batch
    gpu.state.blend_set("ALPHA")
    try:
        shader.uniform_sampler("image", texture)
        batch.draw(shader)
    except Exception as error:
        _texture_draw_failed = True
        print(f"[RAF Scatter] HUD {tag} drawing failed: {error}")
    finally:
        gpu.state.blend_set("NONE")


#----LOGO HELPERS----
def _texture_from_floats(width, height, pixels):
    """Build an RGBA32F GPU texture from a flat float pixel sequence."""
    buffer = gpu.types.Buffer("FLOAT", len(pixels), pixels)
    return gpu.types.GPUTexture((width, height), format="RGBA32F", data=buffer)


def _logo_from_preview():
    """Build the logo texture from the menu preview collection."""
    preview = icon_utils.get_menu_icon_preview(_LOGO_ICON_KEY)
    if preview is None:
        return None
    width, height = preview.image_size
    if width <= 0 or height <= 0:
        return None
    pixels = preview.image_pixels_float
    if len(pixels) != width * height * 4:
        return None
    return _texture_from_floats(width, height, pixels), width, height


def _logo_from_file():
    """Build the logo texture from the addon PNG file."""
    path = os.path.join(_PACKAGE_DIR, "resources", "icons", _LOGO_FILE_NAME)
    if not os.path.isfile(path):
        return None
    image = bpy.data.images.load(path, check_existing=False)
    try:
        width, height = image.size
        if width <= 0 or height <= 0:
            return None
        pixels = image.pixels[:]
        return _texture_from_floats(width, height, pixels), width, height
    finally:
        bpy.data.images.remove(image)


def _try_load_logo():
    """Try both logo sources once and return the texture with its size."""
    for loader in (_logo_from_preview, _logo_from_file):
        try:
            result = loader()
        except Exception as error:
            print(f"[RAF Scatter] HUD logo via {loader.__name__} failed: {error}")
            result = None
        if result is not None:
            return result
    return None


def _get_logo():
    """Return the cached logo texture, loading it lazily when needed."""
    global _logo, _logo_attempts
    if _logo is not None or _logo_attempts >= _LOAD_MAX_ATTEMPTS:
        return _logo
    _logo_attempts += 1
    _logo = _try_load_logo()
    if _logo is None and _logo_attempts >= _LOAD_MAX_ATTEMPTS:
        print("[RAF Scatter] HUD logo unavailable, drawing HUD without it.")
    return _logo


#----PREWARM----
def _tag_view3d_redraw():
    try:
        wm = bpy.context.window_manager
        for window in wm.windows:
            screen = window.screen
            if screen is None:
                continue
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except (AttributeError, RuntimeError):
        pass


def _prewarm_step():
    """Load the logo texture once and tag the viewport for redraw."""
    global _prewarm_ticks, _logo
    _prewarm_ticks += 1
    if _logo is not None:
        return None
    if _prewarm_ticks > _PREWARM_MAX_TICKS:
        print("[RAF Scatter] HUD logo prewarm timed out; HUD will continue without logo.")
        return None
    try:
        start = time.perf_counter()
        _logo = _try_load_logo()
        if _logo is None:
            return _PREWARM_RETRY_INTERVAL
        elapsed = (time.perf_counter() - start) * 1000.0
        print(f"[RAF Scatter] HUD prewarm: logo {elapsed:.1f} ms")
        _tag_view3d_redraw()
        return None
    except Exception as error:
        print(f"[RAF Scatter] HUD prewarm failed: {error}")
        return _PREWARM_RETRY_INTERVAL


def _start_prewarm():
    """Register the logo prewarm timer when a HUD session starts."""
    global _prewarm_ticks
    if bpy.app.background or _logo is not None:
        return
    _prewarm_ticks = 0
    if not bpy.app.timers.is_registered(_prewarm_step):
        bpy.app.timers.register(_prewarm_step, first_interval=_PREWARM_FIRST_DELAY)


def _stop_prewarm():
    """Unregister the logo prewarm timer."""
    if bpy.app.timers.is_registered(_prewarm_step):
        bpy.app.timers.unregister(_prewarm_step)


#----HUD DRAWING----
def _paint_session_active(scene):
    """Return True while a paint session runs on a curve that is in sculpt mode."""
    if not getattr(scene, "scatter_paint_ui_saved", False):
        return False
    curve_obj = scene.scatter_paint_curve_obj
    return curve_obj is not None and curve_obj.mode == 'SCULPT_CURVES'


def _draw_paint_hud():
    """Draw the painting HUD while a paint session is running."""
    scene = bpy.context.scene
    identifier = getattr(scene, "scatter_active_brush", None)
    if identifier is None or not _paint_session_active(scene):
        return
    brush_label = _BRUSH_LABELS.get(identifier, identifier.capitalize())
    hints = [
        (key, action)
        for key, action in _HUD_HINTS
        if key in _BRUSH_HINTS.get(identifier, ())
    ]
    logo = _get_logo()
    logo_w = 0.0
    logo_h = 0.0
    logo_tex = None
    if logo is not None:
        logo_tex, tex_w, tex_h = logo
        aspect = tex_w / tex_h
        logo_h = _HUD_ICON_SIZE
        logo_w = logo_h * aspect
        if logo_w > _HUD_LOGO_MAX_WIDTH:
            logo_w = _HUD_LOGO_MAX_WIDTH
            logo_h = logo_w / aspect
    logo_zone_w = logo_w + _HUD_HEADER_GAP if logo is not None else 0.0
    blf.size(_HUD_FONT_ID, _HUD_HINT_FONT_SIZE)
    action_col_w = max(
        (blf.dimensions(_HUD_FONT_ID, action)[0] for _key, action in hints),
        default=0.0,
    )
    key_col_w = max(
        (blf.dimensions(_HUD_FONT_ID, key)[0] for key, _action in hints),
        default=0.0,
    )
    blf.size(_HUD_FONT_ID, _HUD_FONT_SIZE)
    name_w = blf.dimensions(_HUD_FONT_ID, brush_label)[0]
    name_x_offset = _HUD_PAD + logo_zone_w
    brush_zone_w = name_x_offset + name_w
    hints_zone_w = _HUD_PAD + action_col_w + _HUD_KEY_GAP + key_col_w
    content_w = max(brush_zone_w, hints_zone_w)
    rows_height = (
        _HUD_LINE_HEIGHT * (len(hints) - 1) + _HUD_LAST_ROW_HEIGHT
        if hints else 0.0
    )
    box_w = content_w + _HUD_PAD
    box_h = (
        _HUD_PAD + _HUD_HEADER_HEIGHT + _HUD_DIVIDER_GAP + _HUD_DIVIDER_HEIGHT
        + _HUD_HINT_TOP_GAP + rows_height + _HUD_PAD
    )
    x = _HUD_MARGIN_X
    y = _HUD_BOTTOM_OFFSET
    top = y + box_h
    divider_w = content_w - _HUD_PAD
    _draw_rounded_box(
        x, y, box_w, box_h, _HUD_CORNER_RADIUS, _HUD_BG_COLOR,
    )
    header_cy = top - _HUD_PAD - _HUD_HEADER_HEIGHT * 0.5
    if logo_tex is not None:
        _draw_texture(
            logo_tex, x + _HUD_PAD, header_cy - logo_h * 0.5, logo_w, logo_h, tag="logo",
        )
    blf.size(_HUD_FONT_ID, _HUD_FONT_SIZE)
    blf.color(_HUD_FONT_ID, *_HUD_BRUSH_COLOR)
    blf.position(_HUD_FONT_ID, x + name_x_offset, header_cy - _HUD_FONT_SIZE * 0.35, 0)
    blf.draw(_HUD_FONT_ID, brush_label)
    if not hints:
        return
    divider_y = top - _HUD_PAD - _HUD_HEADER_HEIGHT - _HUD_DIVIDER_GAP
    _draw_box(x + _HUD_PAD, divider_y, divider_w, _HUD_DIVIDER_HEIGHT, _HUD_DIVIDER_COLOR)
    blf.size(_HUD_FONT_ID, _HUD_HINT_FONT_SIZE)
    baseline = divider_y - _HUD_HINT_TOP_GAP
    for key, action in hints:
        blf.color(_HUD_FONT_ID, *_HUD_ACTION_COLOR)
        blf.position(_HUD_FONT_ID, x + _HUD_PAD, baseline, 0)
        blf.draw(_HUD_FONT_ID, action)
        key_w = blf.dimensions(_HUD_FONT_ID, key)[0]
        blf.color(_HUD_FONT_ID, *_HUD_KEY_COLOR)
        blf.position(_HUD_FONT_ID, x + content_w - key_w, baseline, 0)
        blf.draw(_HUD_FONT_ID, key)
        baseline -= _HUD_LINE_HEIGHT


#----HUD LIFECYCLE----
def enable_paint_hud():
    """Install the viewport HUD draw handler and start logo prewarm."""
    global _hud_handle, _texture_draw_failed, _logo_attempts
    if _hud_handle is not None:
        return
    _texture_draw_failed = False
    _logo_attempts = 0
    _hud_handle = bpy.types.SpaceView3D.draw_handler_add(
        _draw_paint_hud, (), "WINDOW", "POST_PIXEL",
    )
    _start_prewarm()


def disable_paint_hud():
    """Remove the viewport handler and keep the cached logo for the session."""
    global _hud_handle, _texture_draw_failed
    _stop_prewarm()
    if _hud_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_hud_handle, "WINDOW")
        _hud_handle = None
    _texture_draw_failed = False


def unload_hud_resources():
    """Release cached HUD GPU resources on addon unload."""
    global _logo, _logo_attempts, _color_shader, _image_shader, _texture_draw_failed
    _stop_prewarm()
    _logo = None
    _logo_attempts = 0
    _box_batch_cache.clear()
    _image_batch_cache.clear()
    _color_shader = None
    _image_shader = None
    _texture_draw_failed = False