"""Surface-aligned brush cursor for RAF Scatter manual painting."""
import math

import bpy
from bpy_extras import view3d_utils
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector


#----CURSOR CONSTANTS----
_RING_SEGMENTS = 48
_RING_COLOR = (1.0, 1.0, 1.0, 0.90)
_NORMAL_COLOR = (1.0, 1.0, 1.0, 0.60)
_DELETE_BRUSH = 'DELETE'
_DELETE_RING_COLOR = (1.0, 0.2, 0.2, 0.90)
_DELETE_NORMAL_COLOR = (1.0, 0.2, 0.2, 0.60)
_RING_LINE_WIDTH = 2.0
_NORMAL_LINE_WIDTH = 1.5
_NORMAL_LENGTH_FACTOR = 0.35
_SURFACE_LIFT_FACTOR = 0.002
_MIN_RADIUS_PX = 1.0
_DEFAULT_RADIUS_PX = 75.0
_BRUSH_SIZE_TO_RADIUS = 0.5  # brush size is a diameter
_RADIUS_REFRESH_INTERVAL = 0.03
_RADIUS_EPSILON_PX = 0.01


#----RUNTIME STATE----
_cursor_handle = None
_draw_failed = False
_line_shader = None
_ring_batch = None
_normal_batch = None
_cursor_region = None
_last_hit = None
_last_radius_px = 0.0
_reported = set()


#----SCENE LOOKUP----
def _get_session_ground(scene):
    """Return the ground object of the paint session's system, if a session is running."""
    if not getattr(scene, "scatter_paint_ui_saved", False):
        return None
    session_curve = scene.scatter_paint_curve_obj
    if session_curve is None or session_curve.mode != 'SCULPT_CURVES':
        return None
    grounds = getattr(scene, "scatter_grounds", None)
    if grounds is None:
        return None
    for ground in grounds:
        for system in ground.scatter_systems:
            if system.curve_obj == session_curve:
                return ground.target_object
    return None


def _report(status):
    """Print a cursor status line once per distinct status."""
    if status in _reported:
        return
    _reported.add(status)
    print(f"[RAF Scatter] Cursor: {status}")


def _get_brush_radius_px(scene):
    """Return the active curves brush radius in pixels, or None if unreadable."""
    paint = getattr(scene.tool_settings, "curves_sculpt", None)
    if paint is None:
        return None
    brush = paint.brush
    unified = getattr(paint, "unified_paint_settings", None)
    use_unified = getattr(unified, "use_unified_size", None)
    if use_unified is None:
        use_unified = getattr(brush, "use_unified_size", False)
    if use_unified and unified is not None:
        return unified.size * _BRUSH_SIZE_TO_RADIUS
    if brush is None:
        return None
    return brush.size * _BRUSH_SIZE_TO_RADIUS


#----GEOMETRY HELPERS----
def _get_line_shader():
    global _line_shader
    if _line_shader is None:
        _line_shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    return _line_shader


def _world_radius(region, rv3d, hit, radius_px):
    """Convert a pixel radius to a world radius at the depth of the hit point."""
    center_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, hit)
    if center_2d is None:
        return None
    edge = view3d_utils.region_2d_to_location_3d(
        region, rv3d, center_2d + Vector((radius_px, 0.0)), hit,
    )
    return (edge - hit).length


def _world_normal(matrix, local_normal):
    """Transform a local-space normal to world space."""
    return (matrix.inverted().transposed().to_3x3() @ local_normal).normalized()


def _build_ring(center, normal, radius):
    """Return a flat circle on the surface tangent plane at the hit point."""
    tangent = normal.cross(Vector((0.0, 0.0, 1.0)))
    if tangent.length < 1e-4:
        tangent = normal.cross(Vector((1.0, 0.0, 0.0)))
    tangent.normalize()
    bitangent = normal.cross(tangent)
    lifted = center + normal * radius * _SURFACE_LIFT_FACTOR
    points = []
    for index in range(_RING_SEGMENTS):
        angle = 2.0 * math.pi * index / _RING_SEGMENTS
        points.append(lifted + (tangent * math.cos(angle) + bitangent * math.sin(angle)) * radius)
    points.append(points[0])  # LINE_STRIP does not close itself
    return points


def _rebuild_cursor(region, rv3d, center, normal, radius_px):
    """Rebuild the ring and normal batches for a hit point; return False if it fails."""
    global _ring_batch, _normal_batch, _cursor_region, _last_hit, _last_radius_px
    radius = _world_radius(region, rv3d, center, radius_px)
    if radius is None or radius <= 0.0:
        return False
    shader = _get_line_shader()
    ring = _build_ring(center, normal, radius)
    tip = center + normal * radius * _NORMAL_LENGTH_FACTOR
    _ring_batch = batch_for_shader(shader, "LINE_STRIP", {"pos": ring})
    _normal_batch = batch_for_shader(shader, "LINES", {"pos": (center, tip)})
    _cursor_region = region
    _last_hit = (center.copy(), normal.copy())
    _last_radius_px = radius_px
    return True


def _find_tracked_view3d():
    """Return the (area, region_3d) pair that owns the tracked region, or None."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for region in area.regions:
                if region == _cursor_region:
                    return area, area.spaces.active.region_3d
    return None


def _tag_view3d_redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


#----CURSOR DRAWING----
def _get_cursor_colors(scene):
    """Return the (ring, normal) colors for the active scatter brush."""
    if getattr(scene, "scatter_active_brush", None) == _DELETE_BRUSH:
        return _DELETE_RING_COLOR, _DELETE_NORMAL_COLOR
    return _RING_COLOR, _NORMAL_COLOR


def _draw_lines(shader, region, batch, color, width):
    shader.bind()
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", width)
    shader.uniform_float("color", color)
    batch.draw(shader)


def _draw_cursor():
    """Draw the surface ring and normal line in the tracked 3D viewport region."""
    global _draw_failed
    region = bpy.context.region
    if _draw_failed or _ring_batch is None or region != _cursor_region:
        return
    shader = _get_line_shader()
    ring_color, normal_color = _get_cursor_colors(bpy.context.scene)
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("NONE")
    try:
        _draw_lines(shader, region, _ring_batch, ring_color, _RING_LINE_WIDTH)
        if _normal_batch is not None:
            _draw_lines(shader, region, _normal_batch, normal_color, _NORMAL_LINE_WIDTH)
    except Exception as error:
        _draw_failed = True
        print(f"[RAF Scatter] Cursor drawing failed: {error}")
    finally:
        gpu.state.blend_set("NONE")


#----CURSOR UPDATE----
def clear_cursor():
    """Hide the surface cursor."""
    global _ring_batch, _normal_batch, _cursor_region, _last_hit
    had_cursor = _ring_batch is not None
    _ring_batch = None
    _normal_batch = None
    _cursor_region = None
    _last_hit = None
    if had_cursor:
        _tag_view3d_redraw()


def _hide(reason):
    clear_cursor()
    _report(reason)


def update_cursor(context, mouse_x, mouse_y):
    """Raycast the ground under the mouse and rebuild the cursor geometry."""
    region = context.region
    rv3d = context.region_data
    ground = _get_session_ground(context.scene)
    if ground is None:
        _hide("no paint session with a target ground")
        return
    if region is None or rv3d is None or region.type != 'WINDOW':
        _hide("tracker has no 3D viewport region")
        return
    if not (0 <= mouse_x < region.width and 0 <= mouse_y < region.height):
        _hide("mouse outside the viewport")
        return
    radius_px = _get_brush_radius_px(context.scene)
    if radius_px is None:
        _report("brush radius unreadable, using default size")
        radius_px = _DEFAULT_RADIUS_PX
    radius_px = max(radius_px, _MIN_RADIUS_PX)
    depsgraph = context.evaluated_depsgraph_get()
    coord = (mouse_x, mouse_y)
    ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
    ray_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    inverse = ground.matrix_world.inverted()
    hit, location, local_normal, _index = ground.ray_cast(
        inverse @ ray_origin, (inverse.to_3x3() @ ray_vector).normalized(), depsgraph=depsgraph,
    )
    if not hit:
        _hide("no ground under the mouse")
        return
    center = ground.matrix_world @ location
    normal = _world_normal(ground.matrix_world, local_normal)
    if not _rebuild_cursor(region, rv3d, center, normal, radius_px):
        _hide("could not convert the brush radius to world size")
        return
    region.tag_redraw()
    _report("tracking")


def _refresh_radius():
    """Timer callback: rebuild the ring at the last hit when the brush size changed."""
    if _last_hit is None or _ring_batch is None:
        return _RADIUS_REFRESH_INTERVAL
    scene = bpy.context.scene
    ground = _get_session_ground(scene)
    radius_px = _get_brush_radius_px(scene)
    if ground is None or radius_px is None:
        return _RADIUS_REFRESH_INTERVAL
    radius_px = max(radius_px, _MIN_RADIUS_PX)
    if abs(radius_px - _last_radius_px) < _RADIUS_EPSILON_PX:
        return _RADIUS_REFRESH_INTERVAL
    view = _find_tracked_view3d()
    if view is None:
        return _RADIUS_REFRESH_INTERVAL
    area, rv3d = view
    center, normal = _last_hit
    if _rebuild_cursor(_cursor_region, rv3d, center, normal, radius_px):
        area.tag_redraw()
    return _RADIUS_REFRESH_INTERVAL


#----CURSOR LIFECYCLE----
def enable_surface_cursor():
    """Install the cursor draw handler and the brush size refresh timer."""
    global _cursor_handle, _draw_failed
    if not bpy.app.timers.is_registered(_refresh_radius):
        bpy.app.timers.register(_refresh_radius, first_interval=_RADIUS_REFRESH_INTERVAL)
    if _cursor_handle is not None:
        return
    _draw_failed = False
    _reported.clear()
    _cursor_handle = bpy.types.SpaceView3D.draw_handler_add(
        _draw_cursor, (), "WINDOW", "POST_VIEW",
    )


def disable_surface_cursor():
    """Remove the cursor draw handler and timer, and hide the cursor."""
    global _cursor_handle
    if bpy.app.timers.is_registered(_refresh_radius):
        bpy.app.timers.unregister(_refresh_radius)
    if _cursor_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_cursor_handle, "WINDOW")
        _cursor_handle = None
    clear_cursor()


def unload_cursor_resources():
    """Release cached cursor GPU resources on addon unload."""
    global _line_shader, _draw_failed
    disable_surface_cursor()
    _line_shader = None
    _draw_failed = False