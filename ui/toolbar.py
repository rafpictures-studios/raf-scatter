"""Paint-session UI overrides: scatter brush tools in the native toolbar, no brush asset shelf."""
import bpy
from bl_keymap_utils import keymap_from_toolbar
from bl_ui.space_toolsystem_common import ToolDef

from ..properties import BRUSH_ICON_NAMES, BRUSH_TYPE_ITEMS
from ..utils import brushes as brush_utils
from ..utils import icons as icon_utils


_TOOLBAR_ORDER = ('LINE', 'DENSITY', 'GROW', 'DELETE', 'SLIDE')
_BRUSH_ITEMS_BY_ID = {item[0]: item for item in BRUSH_TYPE_ITEMS}
_SHELF_CLASS_NAME = "VIEW3D_AST_brush_sculpt_curves"
_FALLBACK_TOOL_ICON = "brush.generic"
_scatter_tool_defs = []
_original_tools_from_context = None
_original_shelf_poll = None
_original_generate = None
_original_brush_type_execute = None
_original_draw_cls = None
_drawing_toolbar = False


#----SESSION CHECK----
def _is_session_curve(context):
    """Return True when the context object is the curve of a starting or running session."""
    scene = getattr(context, "scene", None)
    session_curve = getattr(scene, "scatter_paint_curve_obj", None)
    obj = getattr(context, "object", None) or getattr(context, "active_object", None)
    return session_curve is not None and obj is not None and obj == session_curve


#----SCATTER TOOLS----
def _build_tool_defs():
    """Return the scatter brush tools, separated so the toolbar draws a gap between them."""
    tools = []
    for identifier in _TOOLBAR_ORDER:
        _id, name, description, _icon, _index = _BRUSH_ITEMS_BY_ID[identifier]
        tool_id, brush_type = brush_utils.SCATTER_TOOLS[identifier]
        icon = icon_utils.get_toolbar_icon_handle(BRUSH_ICON_NAMES[identifier])
        if tools:
            tools.append(None)
        tools.append(ToolDef.from_dict({
            "idname": tool_id,
            "label": name,
            "description": description,
            "icon": icon or _FALLBACK_TOOL_ICON,
            "options": {'USE_BRUSHES'},
            "brush_type": brush_type,
        }))
    return tools


def _native_brush_tool(context):
    """Return Blender's own Curves sculpt Brush tool definition, or None."""
    for item in _original_tools_from_context(context, 'SCULPT_CURVES'):
        if item is not None and getattr(item, "idname", None) == brush_utils.NATIVE_CURVES_TOOL:
            return item
    return None


def _tools_from_context(cls, context, mode=None):
    if (
        (mode or context.mode) == 'SCULPT_CURVES'
        and _is_session_curve(context)
        and not brush_utils.is_native_tool_lookup()
    ):
        if not _scatter_tool_defs:
            _scatter_tool_defs.extend(_build_tool_defs())
        yield from _scatter_tool_defs
        # lookups (never drawing) still find Blender's Brush tool, so nothing warns "not found"
        if not _drawing_toolbar:
            native = _native_brush_tool(context)
            if native is not None:
                yield None
                yield native
        return
    yield from _original_tools_from_context(context, mode)


def _draw_cls(cls, layout, context, *args, **kwargs):
    global _drawing_toolbar
    _drawing_toolbar = True
    try:
        return _original_draw_cls(layout, context, *args, **kwargs)
    finally:
        _drawing_toolbar = False


#----BRUSH TYPE TOOL LOOKUP----
def _tool_set_by_brush_type_execute(self, context):
    """Keep a scatter tool active when Blender looks for a tool after a brush change."""
    if not _is_session_curve(context) or brush_utils.is_native_tool_lookup():
        return _original_brush_type_execute(self, context)
    # outside the five scatter brush types Blender would fall back to its own Brush tool,
    # which the session toolbar does not list; stay on the current scatter tool instead
    for tool_id, brush_type in brush_utils.SCATTER_TOOLS.values():
        if brush_type == self.brush_type:
            brush_utils.set_curves_tool(tool_id)
            break
    return {'FINISHED'}


#----TOOLBAR POPUP KEYS----
def _generate_toolbar_keymap(context, space_type, **kwargs):
    """Build the Shift+Space toolbar keymap without auto keys for the scatter tools."""
    keymap = _original_generate(context, space_type, **kwargs)
    if keymap is None:
        return keymap
    # tool tooltips read their "Shortcut" line from this keymap
    for kmi in [kmi for kmi in keymap.keymap_items if kmi.idname == "wm.tool_set_by_id"]:
        if kmi.properties.name in brush_utils.BRUSH_BY_SCATTER_TOOL:
            keymap.keymap_items.remove(kmi)
    return keymap


#----ASSET SHELF----
def _shelf_poll(cls, context):
    if _is_session_curve(context):
        return False
    return _original_shelf_poll(context)


#----PATCHING----
def _patch(cls, name, function):
    """Wrap a classmethod, returning the original even if an earlier load left a patch."""
    current = getattr(cls, name)
    original = getattr(current, "raf_scatter_original", None) or current
    function.raf_scatter_original = original
    setattr(cls, name, classmethod(function))
    return original


def _unpatch(cls, name, original):
    patched = cls.__dict__.get(name)
    if getattr(getattr(patched, "__func__", None), "raf_scatter_original", None) is None:
        return
    setattr(cls, name, classmethod(original.__func__))


def register():
    """Route the Curves sculpt toolbar and brush shelf through the paint session checks."""
    global _original_tools_from_context, _original_shelf_poll, _original_generate
    global _original_brush_type_execute, _original_draw_cls
    _scatter_tool_defs.clear()
    toolbar = bpy.types.VIEW3D_PT_tools_active
    _original_tools_from_context = _patch(toolbar, "tools_from_context", _tools_from_context)
    _original_draw_cls = _patch(toolbar, "draw_cls", _draw_cls)
    brush_type_op = bpy.types.WM_OT_tool_set_by_brush_type
    current_execute = brush_type_op.execute
    _original_brush_type_execute = (
        getattr(current_execute, "raf_scatter_original", None) or current_execute
    )
    _tool_set_by_brush_type_execute.raf_scatter_original = _original_brush_type_execute
    brush_type_op.execute = _tool_set_by_brush_type_execute
    current = keymap_from_toolbar.generate
    _original_generate = getattr(current, "raf_scatter_original", None) or current
    _generate_toolbar_keymap.raf_scatter_original = _original_generate
    keymap_from_toolbar.generate = _generate_toolbar_keymap
    shelf = getattr(bpy.types, _SHELF_CLASS_NAME, None)
    if shelf is None:
        print(f"[RAF Scatter] {_SHELF_CLASS_NAME} not found — asset shelf left as-is")
        return
    _original_shelf_poll = _patch(shelf, "poll", _shelf_poll)


def unregister():
    global _original_tools_from_context, _original_shelf_poll, _original_generate
    global _original_brush_type_execute, _original_draw_cls
    toolbar = bpy.types.VIEW3D_PT_tools_active
    patched_draw = toolbar.__dict__.get("draw_cls")
    if getattr(getattr(patched_draw, "__func__", None), "raf_scatter_original", None) is not None:
        del toolbar.draw_cls
    _original_draw_cls = None
    brush_type_op = bpy.types.WM_OT_tool_set_by_brush_type
    if brush_type_op.__dict__.get("execute") is _tool_set_by_brush_type_execute:
        brush_type_op.execute = _original_brush_type_execute
    _original_brush_type_execute = None
    if _original_generate is not None and keymap_from_toolbar.generate is _generate_toolbar_keymap:
        keymap_from_toolbar.generate = _original_generate
    _original_generate = None
    shelf = getattr(bpy.types, _SHELF_CLASS_NAME, None)
    if shelf is not None and _original_shelf_poll is not None:
        if "poll" in shelf.__dict__ and getattr(shelf.__dict__["poll"].__func__,
                                                "raf_scatter_original", None) is not None:
            del shelf.poll
    if _original_tools_from_context is not None:
        _unpatch(bpy.types.VIEW3D_PT_tools_active, "tools_from_context",
                 _original_tools_from_context)
    _original_tools_from_context = None
    _original_shelf_poll = None
    _scatter_tool_defs.clear()


classes = ()
