"""Manual painting session, brush selection, and brush pie keymap."""
import bpy
from bpy.props import EnumProperty
from bpy.types import Operator

from ..properties import BRUSH_TYPE_ITEMS
from ..utils import brushes as brush_utils
from ..utils import cursor as cursor_utils
from ..utils import hud as hud_utils


_BRUSH_SYNC_INTERVAL = 0.25
_DEFAULT_FALLOFF_SHAPE = 'PROJECTED'
_TRACKER_RESTART_DELAY = 0.02
_BRUSH_DESCRIPTIONS = {item[0]: item[2] for item in BRUSH_TYPE_ITEMS}

_cursor_tracker_token = 0
_tracker_target = None
_last_mouse = None
_resize_anchor = None
_native_cursor_failed = False
_falloff_failed = False
_falloff_applied = set()
_falloff_original = {}
_native_show_brush = {}
_saved_viewport = {}
_brush_pie_keymaps = []
_edit_guard_keymaps = []
_EDIT_MODE_MESSAGE = "Edit Mode is disabled for RAF Scatter paint systems — use Start Painting"


#----SYSTEM LOOKUP----
def _get_active_system(context):
    scene = context.scene
    ground_idx = scene.active_ground_index
    if not (0 <= ground_idx < len(scene.scatter_grounds)):
        return None
    ground = scene.scatter_grounds[ground_idx]
    system_idx = ground.active_scatter_system_index
    if not (0 <= system_idx < len(ground.scatter_systems)):
        return None
    return ground.scatter_systems[system_idx]


def _paint_session_active(scene):
    """Return True while a paint session runs on a curve that is in sculpt mode."""
    if not scene.scatter_paint_ui_saved:
        return False
    curve_obj = scene.scatter_paint_curve_obj
    return curve_obj is not None and curve_obj.mode == 'SCULPT_CURVES'


def is_paint_session_active(scene):
    return _paint_session_active(scene)


#----VIEWPORT STATE----
def _get_view3d_space(context):
    """Return the active 3D viewport space, or the window's first one."""
    space = context.space_data
    if space is not None and space.type == 'VIEW_3D':
        return space
    if context.window is None:
        return None
    for area in context.window.screen.areas:
        if area.type == 'VIEW_3D':
            for sp in area.spaces:
                if sp.type == 'VIEW_3D':
                    return sp
    return None


def _iter_view3d_spaces():
    """Yield every 3D viewport space of every open window."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    yield space


def _adjust_viewport_for_painting(space):
    """Remember the cage overlay state, then hide the cage."""
    saved = _saved_viewport.setdefault(space.as_pointer(), {})
    if saved.get('cage') is None:
        saved['cage'] = space.overlay.show_sculpt_curves_cage
    space.overlay.show_sculpt_curves_cage = False


def _restore_viewport():
    """Give back the cage overlay the session hid."""
    spaces = list(_iter_view3d_spaces())
    live = {space.as_pointer() for space in spaces}
    for key in [key for key in _saved_viewport if key not in live]:
        del _saved_viewport[key]
    for space in spaces:
        key = space.as_pointer()
        saved = _saved_viewport.get(key)
        if saved is None:
            continue
        cage = saved.pop('cage', None)
        if cage is not None:
            space.overlay.show_sculpt_curves_cage = cage
        if not saved:
            del _saved_viewport[key]


#----PAINT SESSION----
def _clear_paint_session(scene):
    scene.scatter_paint_ui_saved = False
    scene.scatter_paint_curve_obj = None


def _watch_paint_sessions(scene, depsgraph):
    """Close paint sessions whose curve left sculpt mode without the Stop button."""
    for scn in bpy.data.scenes:
        if not scn.scatter_paint_ui_saved:
            continue
        curve_obj = scn.scatter_paint_curve_obj
        if curve_obj is None or curve_obj.mode != 'SCULPT_CURVES':
            _clear_paint_session(scn)
            brush_utils.restore_native_curves_tool()


#----CURSOR TRACKING----
def _find_view3d_region(context, space):
    """Return the window, area and WINDOW region hosting the given 3D space."""
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D' or not any(sp == space for sp in area.spaces):
                continue
            for region in area.regions:
                if region.type == 'WINDOW':
                    return window, area, region
    return None


def _start_cursor_tracking(context, space):
    """Start the surface cursor tracker inside the viewport hosting the space."""
    found = _find_view3d_region(context, space)
    if found is None:
        return
    window, area, region = found
    with context.temp_override(window=window, area=area, region=region):
        bpy.ops.scatter.track_surface_cursor('INVOKE_DEFAULT')


def _restart_tracker():
    """Timer callback that adds a fresh tracker above the running brush stroke."""
    if _tracker_target is None or not _paint_session_active(bpy.context.scene):
        return None
    window, area, region = _tracker_target
    try:
        with bpy.context.temp_override(window=window, area=area, region=region):
            bpy.ops.scatter.track_surface_cursor('INVOKE_DEFAULT')
    except (RuntimeError, ReferenceError):
        pass
    return None


def _schedule_tracker_restart(context):
    """Queue a tracker restart once the brush stroke handler has been installed."""
    global _tracker_target
    if bpy.app.timers.is_registered(_restart_tracker):
        return
    _tracker_target = (context.window, context.area, context.region)
    bpy.app.timers.register(_restart_tracker, first_interval=_TRACKER_RESTART_DELAY)


def _radial_control_running(context):
    """Return True while Blender's interactive brush resize is active."""
    return any("radial_control" in op.bl_idname.lower() for op in context.window.modal_operators)


def _event_in_region(context, event):
    region = context.region
    return 0 <= event.mouse_region_x < region.width and 0 <= event.mouse_region_y < region.height


#----NATIVE CURSOR----
def _sync_native_cursor(scene, hide):
    """Hide the native brush circle during a paint session, then restore it."""
    global _native_cursor_failed
    if _native_cursor_failed:
        return
    paint = getattr(scene.tool_settings, "curves_sculpt", None)
    if paint is None:
        return
    saved = _native_show_brush.get(scene.name)
    if hide and saved is None:
        try:
            _native_show_brush[scene.name] = paint.show_brush
            paint.show_brush = False
        except AttributeError:
            _native_cursor_failed = True
            _native_show_brush.pop(scene.name, None)
            print("[RAF Scatter] Native brush cursor cannot be hidden: Paint.show_brush not found")
    elif not hide and saved is not None:
        paint.show_brush = saved
        del _native_show_brush[scene.name]


#----BRUSH FALLOFF----
def _apply_default_falloff(scene):
    """Set projected falloff once on each newly activated curves brush."""
    global _falloff_failed
    if _falloff_failed:
        return
    paint = getattr(scene.tool_settings, "curves_sculpt", None)
    brush = paint.brush if paint is not None else None
    if brush is None:
        return
    key = brush.as_pointer()
    if key in _falloff_applied:
        return
    try:
        _falloff_original.setdefault(key, brush.falloff_shape)
        brush.falloff_shape = _DEFAULT_FALLOFF_SHAPE
    except (AttributeError, TypeError, RuntimeError):
        _falloff_failed = True
        print("[RAF Scatter] Brush falloff shape cannot be set: Brush.falloff_shape unavailable")
        return
    _falloff_applied.add(key)


def _restore_default_falloff():
    """Give each brush back the falloff shape it had before the session."""
    if not _falloff_original:
        return
    for brush in bpy.data.brushes:
        original = _falloff_original.get(brush.as_pointer())
        if original is not None:
            brush.falloff_shape = original
    _falloff_original.clear()
    _falloff_applied.clear()


#----EDIT MODE GUARD----
def is_paint_curve(obj):
    """Return True for the curve object of a RAF Scatter paint system."""
    if obj is None or obj.type != 'CURVES':
        return False
    for scene in bpy.data.scenes:
        for ground in scene.scatter_grounds:
            for system in ground.scatter_systems:
                if system.system_type == 'MANUAL' and system.curve_obj == obj:
                    return True
    return False


def _paint_curves_in_edit_mode():
    return [
        system.curve_obj
        for scene in bpy.data.scenes for ground in scene.scatter_grounds
        for system in ground.scatter_systems
        if system.system_type == 'MANUAL' and system.curve_obj is not None
        and system.curve_obj.mode == 'EDIT'
    ]


def _draw_edit_mode_message(menu, context):
    menu.layout.label(text=_EDIT_MODE_MESSAGE)


def _leave_paint_curve_edit_mode():
    """Timer callback that sends paint curves entered in Edit Mode back to Object Mode."""
    wm = bpy.context.window_manager
    if not _paint_curves_in_edit_mode() or not wm.windows:
        return None
    window = wm.windows[0]
    with bpy.context.temp_override(window=window):
        bpy.ops.object.mode_set(mode='OBJECT')
        wm.popup_menu(_draw_edit_mode_message, title="RAF Scatter", icon='INFO')
    return None


def _guard_paint_curve_edit_mode(scene, depsgraph):
    """Catch Edit Mode entered on a paint curve by any route other than Tab."""
    if _paint_curves_in_edit_mode() and not bpy.app.timers.is_registered(
        _leave_paint_curve_edit_mode
    ):
        # mode changes are not allowed while the depsgraph is being updated
        bpy.app.timers.register(_leave_paint_curve_edit_mode, first_interval=0.0)


def _register_edit_guard_keymap():
    """Route Tab through the edit-mode guard before Blender's own mode toggle."""
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm is not None else None
    if kc is None:
        return
    km = kc.keymaps.new(name="Object Non-modal")
    kmi = km.keymap_items.new("scatter.guard_edit_mode", 'TAB', 'PRESS')
    _edit_guard_keymaps.append((km, kmi))


def _unregister_edit_guard_keymap():
    for km, kmi in _edit_guard_keymaps:
        km.keymap_items.remove(kmi)
    _edit_guard_keymaps.clear()


#----BRUSH PIE KEYMAP----
def _register_brush_pie_keymap():
    """Bind Alt+Shift+W to the brush pie in the 3D viewport."""
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm is not None else None
    if kc is None:
        print("[RAF Scatter] Brush pie NOT registered — no addon keyconfig available; "
              "restart Blender once")
        return
    km = kc.keymaps.new(name="3D View Generic", space_type='VIEW_3D')
    kmi = km.keymap_items.new("scatter.call_brush_pie", 'W', 'PRESS', alt=True, shift=True)
    _brush_pie_keymaps.append((km, kmi))
    print("[RAF Scatter] Brush pie registered: Alt+Shift+W in the 3D viewport")


def _unregister_brush_pie_keymap():
    for km, kmi in _brush_pie_keymaps:
        km.keymap_items.remove(kmi)
    _brush_pie_keymaps.clear()


#----SESSION END----
def end_paint_session(context):
    """Close the paint session and hand the viewport back to Blender's defaults."""
    scene = context.scene
    _clear_paint_session(scene)
    brush_utils.sync_scatter_tool(scene, False)
    cursor_utils.clear_cursor()
    _sync_native_cursor(scene, False)
    _restore_default_falloff()
    _restore_viewport()


#----BRUSH SYNC----
def _brush_sync_poll():
    """Repeating timer that applies session settings and restores Blender defaults outside it."""
    any_session = False
    context_scene = bpy.context.scene
    if context_scene is not None:
        brush_utils.sync_scatter_tool(context_scene, _paint_session_active(context_scene))
    for scene in bpy.data.scenes:
        if _paint_session_active(scene):
            any_session = True
            brush_utils.ensure_active_brush(scene)
            _apply_default_falloff(scene)
            _sync_native_cursor(scene, True)
        else:
            _sync_native_cursor(scene, False)
    if not any_session:
        _restore_default_falloff()
        _restore_viewport()
    return _BRUSH_SYNC_INTERVAL


class SCATTER_OT_start_manual_paint(Operator):
    bl_idname = "scatter.start_manual_paint"
    bl_label = "Start Painting"
    bl_description = "Enter Curves sculpt mode on the active paint system to paint scatter points"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        system = _get_active_system(context)
        return (
            system is not None
            and system.system_type == 'MANUAL'
            and system.curve_obj is not None
        )

    def execute(self, context):
        system = _get_active_system(context)
        curve_obj = system.curve_obj
        scene = context.scene
        if _paint_session_active(scene) and scene.scatter_paint_curve_obj == curve_obj:
            end_paint_session(context)
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'FINISHED'}
        if curve_obj.hide_viewport:
            self.report(
                {'WARNING'}, "Curve object is hidden in the viewport — unhide the system first"
            )
            return {'CANCELLED'}
        space = _get_view3d_space(context)
        if space is None:
            self.report({'WARNING'}, "No 3D viewport available")
            return {'CANCELLED'}
        if scene.scatter_paint_ui_saved:
            _clear_paint_session(scene)
        active = context.view_layer.objects.active
        if active is not None and active.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in context.selected_objects:
            obj.select_set(False)
        curve_obj.select_set(True)
        context.view_layer.objects.active = curve_obj
        scene.scatter_paint_curve_obj = curve_obj
        _adjust_viewport_for_painting(space)
        bpy.ops.object.mode_set(mode='SCULPT_CURVES')
        brush_utils.apply_active_brush(scene)
        brush_utils.activate_scatter_tool(scene.scatter_active_brush)
        brush_utils.select_all_curve_points(context)
        _falloff_applied.clear()
        _apply_default_falloff(scene)
        # set last so depsgraph runs during execute never see a session in OBJECT mode
        scene.scatter_paint_ui_saved = True
        _sync_native_cursor(scene, True)
        _start_cursor_tracking(context, space)
        return {'FINISHED'}


class SCATTER_OT_stop_manual_paint(Operator):
    bl_idname = "scatter.stop_manual_paint"
    bl_label = "Exit Paint Mode"
    bl_description = "Leave curves sculpt mode and close the paint session"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return _paint_session_active(context.scene)

    def execute(self, context):
        end_paint_session(context)
        bpy.ops.object.mode_set(mode='OBJECT')
        return {'FINISHED'}


class SCATTER_OT_guard_edit_mode(Operator):
    bl_idname = "scatter.guard_edit_mode"
    bl_label = "Toggle Edit Mode"
    bl_description = "Toggle Edit Mode, except on RAF Scatter paint curves"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        active = context.view_layer.objects.active
        if active is None or active.type != 'CURVES' or active.mode == 'EDIT':
            return {'PASS_THROUGH'}
        if active.mode == 'SCULPT_CURVES' and is_paint_curve(active):
            if _paint_session_active(context.scene):
                end_paint_session(context)
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'FINISHED'}
        if active.mode == 'OBJECT' and any(
            is_paint_curve(obj) for obj in [active, *context.selected_objects]
        ):
            self.report({'WARNING'}, _EDIT_MODE_MESSAGE)
            return {'CANCELLED'}
        return {'PASS_THROUGH'}


class SCATTER_OT_call_brush_pie(Operator):
    bl_idname = "scatter.call_brush_pie"
    bl_label = "Brush Pie"
    bl_description = "Open the scatter brush pie menu while painting"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return _paint_session_active(context.scene)

    def invoke(self, context, event):
        bpy.ops.wm.call_menu_pie('INVOKE_DEFAULT', name="SCATTER_MT_brush_pie")
        return {'FINISHED'}


class SCATTER_OT_set_brush(Operator):
    bl_idname = "scatter.set_brush"
    bl_label = "Set Brush"
    bl_description = "Select the scatter brush"
    bl_options = {'REGISTER'}

    brush: EnumProperty(items=BRUSH_TYPE_ITEMS)

    @classmethod
    def description(cls, context, properties):
        return _BRUSH_DESCRIPTIONS.get(properties.brush, cls.bl_description)

    def execute(self, context):
        scene = context.scene
        if scene.scatter_active_brush == self.brush:
            brush_utils.select_all_curve_points(context)
        else:
            scene.scatter_active_brush = self.brush
        return {'FINISHED'}


class SCATTER_OT_track_surface_cursor(Operator):
    bl_idname = "scatter.track_surface_cursor"
    bl_label = "Track Surface Cursor"
    bl_description = "Follow the mouse over the ground while painting scatter points"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        global _cursor_tracker_token
        _cursor_tracker_token += 1
        self._token = _cursor_tracker_token
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        global _last_mouse, _resize_anchor
        if self._token != _cursor_tracker_token:
            return {'CANCELLED', 'PASS_THROUGH'}
        if not _paint_session_active(context.scene):
            cursor_utils.clear_cursor()
            return {'CANCELLED', 'PASS_THROUGH'}
        if event.type == 'MOUSEMOVE':
            if _radial_control_running(context):
                if _resize_anchor is None:
                    _resize_anchor = _last_mouse
                if _resize_anchor is not None:
                    cursor_utils.update_cursor(context, *_resize_anchor)
            else:
                _resize_anchor = None
                _last_mouse = (event.mouse_region_x, event.mouse_region_y)
                cursor_utils.update_cursor(context, *_last_mouse)
        elif event.value == 'PRESS' and _event_in_region(context, event) and (
            event.type == 'LEFTMOUSE'
            or (event.type == 'F' and not (event.shift or event.ctrl or event.alt))
        ):
            _schedule_tracker_restart(context)
        return {'PASS_THROUGH'}


classes = (
    SCATTER_OT_start_manual_paint,
    SCATTER_OT_stop_manual_paint,
    SCATTER_OT_guard_edit_mode,
    SCATTER_OT_call_brush_pie,
    SCATTER_OT_set_brush,
    SCATTER_OT_track_surface_cursor,
)


def register():
    bpy.app.handlers.depsgraph_update_post.append(_watch_paint_sessions)
    bpy.app.handlers.depsgraph_update_post.append(_guard_paint_curve_edit_mode)
    _register_brush_pie_keymap()
    _register_edit_guard_keymap()
    hud_utils.enable_paint_hud()
    cursor_utils.enable_surface_cursor()
    bpy.app.timers.register(_brush_sync_poll, first_interval=_BRUSH_SYNC_INTERVAL)


def unregister():
    global _cursor_tracker_token
    brush_utils.restore_native_curves_tool()
    _unregister_brush_pie_keymap()
    _unregister_edit_guard_keymap()
    if bpy.app.timers.is_registered(_leave_paint_curve_edit_mode):
        bpy.app.timers.unregister(_leave_paint_curve_edit_mode)
    if _guard_paint_curve_edit_mode in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_guard_paint_curve_edit_mode)
    hud_utils.disable_paint_hud()
    _cursor_tracker_token += 1
    cursor_utils.unload_cursor_resources()
    if bpy.app.timers.is_registered(_restart_tracker):
        bpy.app.timers.unregister(_restart_tracker)
    if bpy.app.timers.is_registered(_brush_sync_poll):
        bpy.app.timers.unregister(_brush_sync_poll)
    for scene in bpy.data.scenes:
        _sync_native_cursor(scene, False)
    _restore_default_falloff()
    _restore_viewport()
    if _watch_paint_sessions in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_watch_paint_sessions)