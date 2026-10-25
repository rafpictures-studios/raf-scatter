"""Brush mapping and activation helpers for RAF Scatter."""
import os

import bpy


#----BRUSH MAPPINGS----
BRUSH_TO_NATIVE_NAME = {
    'LINE': "Add",
    'DENSITY': "Density",
    'GROW': "Grow/Shrink",
    'DELETE': "Delete",
    'SLIDE': "Slide",
}
BRUSH_TO_CURVES_TOOL = {
    'LINE': "ADD",
    'DENSITY': "DENSITY",
    'GROW': "GROW_SHRINK",
    'DELETE': "DELETE",
    'SLIDE': "SLIDE",
}
BRUSH_TO_TOOL_IDS = {
    'LINE': ("builtin.draw", "builtin.add"),
    'DENSITY': ("builtin.density",),
    'GROW': ("builtin.grow_shrink", "builtin.grow"),
    'DELETE': ("builtin.delete",),
    'SLIDE': ("builtin.slide",),
}
SCATTER_TOOLS = {
    'LINE': ("raf_scatter.brush_add", 'ADD'),
    'DENSITY': ("raf_scatter.brush_density", 'DENSITY'),
    'GROW': ("raf_scatter.brush_grow", 'GROW_SHRINK'),
    'DELETE': ("raf_scatter.brush_delete", 'DELETE'),
    'SLIDE': ("raf_scatter.brush_slide", 'SLIDE'),
}
BRUSH_BY_SCATTER_TOOL = {tool_id: identifier for identifier, (tool_id, _t) in SCATTER_TOOLS.items()}
NATIVE_CURVES_TOOL = "builtin.brush"
_native_tool_lookup = False
_ESSENTIALS_BRUSH_DIR = ("brushes", "essentials_brushes-curve_sculpt.blend", "Brush")
_BRUSH_NAME_PREFIX = "Scatter "
_BRUSH_ATTEMPTS = 2
_brush_type_original = {}


#----BRUSH TYPE----
def brush_type(brush):
    """Curves sculpt type of a brush; the property was renamed in Blender 5.0."""
    if brush is None:
        return None
    if hasattr(brush, "curves_sculpt_brush_type"):
        return brush.curves_sculpt_brush_type
    return getattr(brush, "curves_sculpt_tool", None)


def _set_brush_type(brush, value):
    if hasattr(brush, "curves_sculpt_brush_type"):
        brush.curves_sculpt_brush_type = value
    else:
        brush.curves_sculpt_tool = value


def _active_brush(scene):
    try:
        return scene.tool_settings.curves_sculpt.brush
    except AttributeError:
        return None


def _has_brush_type(scene, identifier):
    return brush_type(_active_brush(scene)) == BRUSH_TO_CURVES_TOOL[identifier]


def _correct_brush_type(scene, identifier):
    """Give an edited brush (e.g. a Slide set to Comb) the scatter type for this session only."""
    brush = _active_brush(scene)
    expected = BRUSH_TO_CURVES_TOOL[identifier]
    if brush is None or brush_type(brush) == expected or not brush.is_editable:
        return False
    _brush_type_original.setdefault(brush.as_pointer(), brush_type(brush))
    _set_brush_type(brush, expected)
    return True


def restore_brush_types():
    """Give the brushes corrected during the session their own type back."""
    if not _brush_type_original:
        return
    for brush in bpy.data.brushes:
        original = _brush_type_original.get(brush.as_pointer())
        if original is not None and brush.is_editable:
            _set_brush_type(brush, original)
    _brush_type_original.clear()


#----SCULPTING STATE----
def _any_system_sculpting(scene):
    """Return True when any scatter system is in curves sculpt mode."""
    grounds = getattr(scene, "scatter_grounds", None)
    if grounds is None:
        return False
    for ground in grounds:
        for system in ground.scatter_systems:
            curve_obj = system.curve_obj
            if curve_obj is not None and curve_obj.mode == 'SCULPT_CURVES':
                return True
    return False


#----BRUSH ACTIVATION----
def _activate_brush_asset(identifier):
    """Activate the matching native brush through the Essentials asset."""
    native_name = BRUSH_TO_NATIVE_NAME.get(identifier)
    if native_name is None:
        return False
    asset_path = _ESSENTIALS_BRUSH_DIR + (native_name,)
    for separator in (os.sep, "\\", "/"):
        try:
            bpy.ops.brush.asset_activate(
                asset_library_type="ESSENTIALS", asset_library_identifier="",
                relative_asset_identifier=separator.join(asset_path),
            )
            return True
        except (RuntimeError, TypeError):
            continue
    return False


def _activate_workspace_tool(identifier):
    """Activate a workspace tool as a fallback brush selection method."""
    for tool_id in BRUSH_TO_TOOL_IDS[identifier]:
        try:
            bpy.ops.wm.tool_set_by_id(name=tool_id)
            return True
        except (RuntimeError, AttributeError):
            continue
    return False


def _create_curves_brush(name):
    """Create a curves sculpt brush using the available Blender mode ID."""
    for mode in ('CURVES_SCULPT', 'SCULPT_CURVES'):
        try:
            return bpy.data.brushes.new(name, mode=mode)
        except TypeError:
            continue
    return bpy.data.brushes.new(name)


def _ensure_curves_brush(identifier):
    """Return a suitable curves sculpt brush for the given identifier."""
    native_name = BRUSH_TO_NATIVE_NAME.get(identifier)
    if native_name is not None:
        native = bpy.data.brushes.get(native_name)
        if native is not None and brush_type(native) == BRUSH_TO_CURVES_TOOL[identifier]:
            return native
    tool = BRUSH_TO_CURVES_TOOL[identifier]
    name = _BRUSH_NAME_PREFIX + tool.replace("_", " ").title()
    brush = bpy.data.brushes.get(name)
    if brush is not None:
        return brush
    brush = _create_curves_brush(name)
    _set_brush_type(brush, tool)
    return brush


def _assign_brush_pointer(scene, identifier):
    """Assign the matching brush through a writable tool settings pointer."""
    for path in ('curves_sculpt', 'paint_mode'):
        settings = getattr(scene.tool_settings, path, None)
        if settings is None:
            continue
        try:
            settings.brush = settings.brush
        except (AttributeError, TypeError):
            continue
        settings.brush = _ensure_curves_brush(identifier)
        return True
    return False


#----ACTIVE BRUSH----
def ensure_active_brush(scene):
    """Keep the native brush aligned with the addon selection while sculpting."""
    identifier = getattr(scene, "scatter_active_brush", None)
    if identifier not in BRUSH_TO_NATIVE_NAME:
        return
    if not _any_system_sculpting(scene):
        return
    if _has_brush_type(scene, identifier):
        return
    if get_active_curves_tool_id(bpy.context) in BRUSH_BY_SCATTER_TOOL:
        _activate_brush_asset_for_scatter_tool(identifier)
    elif not _activate_brush_asset(identifier) and not _activate_workspace_tool(identifier):
        _assign_brush_pointer(scene, identifier)
    _correct_brush_type(scene, identifier)


#----SCATTER TOOLS----
def get_active_curves_tool_id(context):
    """Return the idname of the workspace tool used in Curves sculpt mode, or None."""
    workspace = getattr(context, "workspace", None)
    if workspace is None:
        return None
    tool = workspace.tools.from_space_view3d_mode('SCULPT_CURVES', create=False)
    return tool.idname if tool is not None else None


def set_curves_tool(tool_id):
    """Make a tool active in Curves sculpt mode; return False when it cannot be set."""
    if bpy.context.mode != 'SCULPT_CURVES':
        return False
    window = bpy.context.window or next(iter(bpy.context.window_manager.windows), None)
    if window is None:
        return False
    try:
        with bpy.context.temp_override(window=window):
            return 'FINISHED' in bpy.ops.wm.tool_set_by_id(name=tool_id, space_type='VIEW_3D')
    except RuntimeError:
        return False


def is_native_tool_lookup():
    """Return True while a brush asset is activated and must see Blender's own tools."""
    return _native_tool_lookup


def _activate_brush_asset_for_scatter_tool(identifier):
    """Activate the scatter brush asset and tool, again when the tool switch swapped the brush."""
    global _native_tool_lookup
    scene = bpy.context.scene
    for _attempt in range(_BRUSH_ATTEMPTS):
        _native_tool_lookup = True
        try:
            activated = _activate_brush_asset(identifier)
        finally:
            _native_tool_lookup = False
        tool_set = set_curves_tool(SCATTER_TOOLS[identifier][0])
        if activated and tool_set and _has_brush_type(scene, identifier):
            return True
    return activated and _correct_brush_type(scene, identifier)


def activate_scatter_tool(identifier):
    """Show the scatter brush as the active toolbar tool."""
    tool_id = SCATTER_TOOLS.get(identifier, (None, None))[0]
    if tool_id is None or get_active_curves_tool_id(bpy.context) == tool_id:
        return
    set_curves_tool(tool_id)


def restore_native_curves_tool():
    """Point every workspace's Curves sculpt tool back at Blender's Brush tool if it is ours."""
    for workspace in bpy.data.workspaces:
        tool = workspace.tools.from_space_view3d_mode('SCULPT_CURVES', create=False)
        if tool is None or tool.idname not in BRUSH_BY_SCATTER_TOOL:
            continue
        tool.setup(
            idname=NATIVE_CURVES_TOOL, cursor='DEFAULT', keymap="", gizmo_group="",
            brush_type='ANY', data_block="", operator="", index=0, options={'USE_BRUSHES'},
            idname_fallback="", keymap_fallback="",
        )


def sync_scatter_tool(scene, in_session):
    """Keep the toolbar tool and the scatter brush in step; give the native tool back after."""
    if not in_session:
        restore_native_curves_tool()
        return
    tool_id = get_active_curves_tool_id(bpy.context)
    picked = BRUSH_BY_SCATTER_TOOL.get(tool_id)
    if picked is None:
        activate_scatter_tool(scene.scatter_active_brush)
    elif picked != scene.scatter_active_brush:
        scene.scatter_active_brush = picked


def select_all_curve_points(context):
    """Select every point of the sculpted curves, like pressing A, so brushes act on all."""
    obj = context.active_object
    if obj is None or obj.type != 'CURVES' or obj.mode != 'SCULPT_CURVES':
        return
    try:
        bpy.ops.curves.select_all(action='SELECT')
    except RuntimeError:
        pass


def apply_active_brush(scene, context=None):
    """Apply the selected native brush to the active scatter paint session."""
    identifier = scene.scatter_active_brush
    if identifier not in BRUSH_TO_NATIVE_NAME:
        return False
    curve_obj = scene.scatter_paint_curve_obj
    if curve_obj is None or curve_obj.mode != 'SCULPT_CURVES':
        return False
    if _activate_brush_asset_for_scatter_tool(identifier):
        return True
    if _activate_brush_asset(identifier) or _activate_workspace_tool(identifier):
        _correct_brush_type(scene, identifier)
        return True
    if _assign_brush_pointer(scene, identifier):
        return True
    print(
        f"[RAF Scatter] Could not activate the curves sculpt brush for '{identifier}' "
        f"(asset activation, tool switching and pointer fallback all failed)."
    )
    try:
        curves_sculpt = scene.tool_settings.curves_sculpt
        active = curves_sculpt.brush.name if curves_sculpt.brush else None
        print(f"[RAF Scatter] context.mode: {bpy.context.mode} | active brush: {active}")
    except (AttributeError, RuntimeError):
        pass
    return False