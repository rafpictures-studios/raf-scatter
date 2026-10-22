"""Operators for target ground management and the delete guard of ground objects."""
import bpy
from bpy.props import IntProperty
from bpy.types import Operator

from .system_ops import remove_system_curve


_DELETE_GUARD_KEYS = (
    ("Object Mode", 'EMPTY', 'X'), ("Object Mode", 'EMPTY', 'DEL'),
    ("Outliner", 'OUTLINER', 'X'), ("Outliner", 'OUTLINER', 'DEL'),
)
_delete_guard_keymaps = []
_cleanup_report = []


#----GROUND HELPERS----
def _tag_redraw_viewport(context):
    if context.screen is None:
        return
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def _ground_stats(grounds):
    systems = sum(len(ground.scatter_systems) for ground in grounds)
    masks = sum(len(system.effectors) for ground in grounds for system in ground.scatter_systems)
    return systems, masks


def remove_ground(context, index):
    """Remove a target ground entry and every scatter system built on it (the mesh is kept)."""
    scene = context.scene
    ground = scene.scatter_grounds[index]
    curve_objects = [system.curve_obj for system in ground.scatter_systems]
    ground.scatter_systems.clear()
    for curve_obj in curve_objects:
        remove_system_curve(context, curve_obj)
    scene.scatter_grounds.remove(index)
    last = len(scene.scatter_grounds) - 1
    scene.active_ground_index = max(0, min(scene.active_ground_index, last))


def _is_already_ground(scene, obj):
    """Return True if the object is already a target ground."""
    for ground in scene.scatter_grounds:
        if ground.target_object == obj:
            return True
    return False


def _add_ground(context, obj):
    """Register an object as a target ground."""
    scene = context.scene
    ground = scene.scatter_grounds.add()
    ground.name = obj.name
    ground.target_object = obj
    scene.scatter_grounds.move(len(scene.scatter_grounds) - 1, 0)
    scene.active_ground_index = 0
    _tag_redraw_viewport(context)


#----OPERATORS----
class SCATTER_OT_add_ground_popup(Operator):
    bl_idname = "scatter.add_ground_popup"
    bl_label = "Add Target Ground"
    bl_description = "Add a target ground chosen from a popup picker"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        context.scene.scatter_ground_picker_temp = None
        return context.window_manager.invoke_props_dialog(self, width=260)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Target Ground")
        layout.prop(context.scene, "scatter_ground_picker_temp", text="")

    def execute(self, context):
        scene = context.scene
        obj = scene.scatter_ground_picker_temp
        if obj is None:
            self.report({'WARNING'}, "No object selected")
            return {'CANCELLED'}
        if _is_already_ground(scene, obj):
            self.report({'WARNING'}, f"'{obj.name}' is already a Target Ground")
            return {'CANCELLED'}
        _add_ground(context, obj)
        scene.scatter_ground_picker_temp = None
        return {'FINISHED'}


class SCATTER_OT_add_ground_from_selected(Operator):
    bl_idname = "scatter.add_ground_from_selected"
    bl_label = "Add Selected as Ground"
    bl_description = "Add the currently active mesh object as a Target Ground"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            return False
        return not _is_already_ground(context.scene, obj)

    def execute(self, context):
        _add_ground(context, context.active_object)
        return {'FINISHED'}


class SCATTER_OT_set_active_ground(Operator):
    bl_idname = "scatter.set_active_ground"
    bl_label = "Set active ground"
    bl_description = "Set the active target ground by index"
    bl_options = {'INTERNAL'}

    index: IntProperty()

    def execute(self, context):
        context.scene.active_ground_index = self.index
        _tag_redraw_viewport(context)
        return {'FINISHED'}


class SCATTER_OT_select_ground(Operator):
    bl_idname = "scatter.select_ground"
    bl_label = "Select Ground"
    bl_description = "Select the active Target Ground object in the viewport"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        return 0 <= scene.active_ground_index < len(scene.scatter_grounds)

    def execute(self, context):
        scene = context.scene
        idx = scene.active_ground_index
        ground = scene.scatter_grounds[idx]
        obj = ground.target_object
        if obj is None:
            return {'CANCELLED'}
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {'FINISHED'}


class SCATTER_OT_delete_ground(Operator):
    bl_idname = "scatter.delete_ground"
    bl_label = "Delete ground"
    bl_description = "Remove the active target ground and every scatter system built on it"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        return 0 <= scene.active_ground_index < len(scene.scatter_grounds)

    def invoke(self, context, event):
        ground = context.scene.scatter_grounds[context.scene.active_ground_index]
        systems = len(ground.scatter_systems)
        effectors = sum(len(system.effectors) for system in ground.scatter_systems)
        return context.window_manager.invoke_confirm(
            self, event, title=f"Delete Ground \"{ground.name}\"",
            message=f"Also deletes {systems} scatter system(s) and {effectors} mask(s)."
                    "The ground mesh itself is kept.",
            confirm_text="Delete", icon='WARNING',
        )

    def execute(self, context):
        scene = context.scene
        idx = scene.active_ground_index
        remove_ground(context, idx)
        scene.active_ground_index = max(0, idx - 1)
        _tag_redraw_viewport(context)
        return {'FINISHED'}


#----DELETE GUARD----
def _objects_to_delete(context):
    """Return the objects a Delete in this editor would remove."""
    if context.area is not None and context.area.type == 'OUTLINER':
        ids = getattr(context, "selected_ids", None) or ()
        return [idb for idb in ids if isinstance(idb, bpy.types.Object)]
    return list(context.selected_objects)


def _grounds_of(scene, objects):
    names = {obj.name for obj in objects}
    return [
        index for index, ground in enumerate(scene.scatter_grounds)
        if ground.target_object is not None and ground.target_object.name in names
    ]


class SCATTER_OT_guard_delete(Operator):
    bl_idname = "scatter.guard_delete"
    bl_label = "Delete"
    bl_description = "Delete the selected objects, warning first when one is a RAF Scatter ground"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    def invoke(self, context, event):
        indices = _grounds_of(context.scene, _objects_to_delete(context))
        if not indices:
            return {'PASS_THROUGH'}
        grounds = [context.scene.scatter_grounds[index] for index in indices]
        systems, masks = _ground_stats(grounds)
        names = ", ".join(f'"{ground.name}"' for ground in grounds)
        return context.window_manager.invoke_confirm(
            self, event, title="Delete Target Ground",
            message=f"{names} is a RAF Scatter Target Ground. Deleting it also removes "
                    f"{systems} scatter system(s) and {masks} mask(s).",
            confirm_text="Delete", icon='WARNING',
        )

    def execute(self, context):
        scene = context.scene
        for index in sorted(_grounds_of(scene, _objects_to_delete(context)), reverse=True):
            remove_ground(context, index)
        if context.area is not None and context.area.type == 'OUTLINER':
            bpy.ops.outliner.delete()
        else:
            bpy.ops.object.delete(confirm=False)
        _tag_redraw_viewport(context)
        return {'FINISHED'}


def _show_cleanup_report(menu, context):
    for line in _cleanup_report:
        menu.layout.label(text=line)


def _remove_lost_grounds(scene):
    """Remove the grounds of a scene whose mesh no longer exists; return systems removed."""
    lost = [i for i, ground in enumerate(scene.scatter_grounds) if ground.target_object is None]
    if not lost:
        return 0
    systems, _masks = _ground_stats([scene.scatter_grounds[i] for i in lost])
    with bpy.context.temp_override(scene=scene):
        for index in reversed(lost):
            remove_ground(bpy.context, index)
    return systems


def _clean_deleted_grounds():
    """Timer callback: drop grounds whose mesh was deleted another way, with their systems."""
    wm = bpy.context.window_manager
    window = wm.windows[0] if wm.windows else None
    _cleanup_report.clear()
    for scene in bpy.data.scenes:
        if not any(ground.target_object is None for ground in scene.scatter_grounds):
            continue
        if window is not None:
            with bpy.context.temp_override(window=window):
                systems = _remove_lost_grounds(scene)
        else:
            systems = _remove_lost_grounds(scene)
        _cleanup_report.append(
            f"A Target Ground was deleted: {systems} scatter system(s) were removed with it."
        )
    if _cleanup_report and window is not None:
        with bpy.context.temp_override(window=window):
            bpy.ops.ed.undo_push(message="Remove scatter of a deleted ground")
            wm.popup_menu(_show_cleanup_report, title="RAF Scatter", icon='INFO')
    return None


def _watch_deleted_grounds(scene, depsgraph):
    """Catch ground meshes deleted by any route the delete guard does not see."""
    lost = any(g.target_object is None for s in bpy.data.scenes for g in s.scatter_grounds)
    if lost and not bpy.app.timers.is_registered(_clean_deleted_grounds):
        # objects cannot be removed while the depsgraph is being updated
        bpy.app.timers.register(_clean_deleted_grounds, first_interval=0.0)


classes = (
    SCATTER_OT_add_ground_popup,
    SCATTER_OT_add_ground_from_selected,
    SCATTER_OT_set_active_ground,
    SCATTER_OT_select_ground,
    SCATTER_OT_delete_ground,
    SCATTER_OT_guard_delete,
)


def register():
    bpy.app.handlers.depsgraph_update_post.append(_watch_deleted_grounds)
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon if wm is not None else None
    if kc is None:
        return
    for keymap_name, space_type, key in _DELETE_GUARD_KEYS:
        km = kc.keymaps.new(name=keymap_name, space_type=space_type)
        kmi = km.keymap_items.new("scatter.guard_delete", key, 'PRESS')
        _delete_guard_keymaps.append((km, kmi))


def unregister():
    for km, kmi in _delete_guard_keymaps:
        km.keymap_items.remove(kmi)
    _delete_guard_keymaps.clear()
    if bpy.app.timers.is_registered(_clean_deleted_grounds):
        bpy.app.timers.unregister(_clean_deleted_grounds)
    if _watch_deleted_grounds in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_watch_deleted_grounds)