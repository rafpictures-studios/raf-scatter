import bpy
from bpy.types import Operator
from bpy.props import IntProperty


def _tag_redraw_viewport(context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def _is_already_ground(scene, obj):
    """Rule F: one object can only be a Target Ground once."""
    for ground in scene.scatter_grounds:
        if ground.target_object == obj:
            return True
    return False


def _add_ground(context, obj):
    scene = context.scene
    ground = scene.scatter_grounds.add()
    ground.name = obj.name
    ground.target_object = obj

    scene.scatter_grounds.move(len(scene.scatter_grounds) - 1, 0)
    scene.active_ground_index = 0

    _tag_redraw_viewport(context)


class SCATTER_OT_add_ground_popup(Operator):
    bl_idname = "scatter.add_ground_popup"
    bl_label = "Add Target Ground"
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
    """Adds the active selected mesh object directly as a Target
    Ground, skipping the picker dialog. Grayed out (poll fails)
    whenever the active object isn't a MESH, or is already used as a
    Target Ground elsewhere (Rule F)."""
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
    bl_options = {'INTERNAL'}

    index: IntProperty()

    def execute(self, context):
        context.scene.active_ground_index = self.index
        _tag_redraw_viewport(context)
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
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        scene = context.scene
        idx = scene.active_ground_index
        ground = scene.scatter_grounds[idx]

        for system in ground.scatter_systems:
            if system.curve_obj:
                bpy.data.objects.remove(system.curve_obj, do_unlink=True)

        scene.scatter_grounds.remove(idx)
        scene.active_ground_index = max(0, idx - 1)

        _tag_redraw_viewport(context)
        return {'FINISHED'}


classes = (
    SCATTER_OT_add_ground_popup,
    SCATTER_OT_add_ground_from_selected,
    SCATTER_OT_set_active_ground,
    SCATTER_OT_delete_ground,
)