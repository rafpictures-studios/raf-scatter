import bpy
from bpy.types import Operator
from bpy.props import IntProperty, PointerProperty


class SCATTER_OT_add_ground_popup(Operator):
    bl_idname = "scatter.add_ground_popup"
    bl_label = "Target Ground"
    bl_property = "ground_object"

    ground_object: PointerProperty(
        name="Ground",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == 'MESH'
    )

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_search_popup(self)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Target Ground")
        layout.separator(factor=0.5)
        layout.prop(self, "ground_object", text="")

    def execute(self, context):
        if self.ground_object:
            scene = context.scene
            scene.scatter_ground_picker_temp = self.ground_object
            
            ground = scene.scatter_grounds.add()
            ground.name = self.ground_object.name
            ground.target_object = self.ground_object
            
            scene.scatter_grounds.move(len(scene.scatter_grounds) - 1, 0)
            scene.active_ground_index = 0
            scene.scatter_ground_picker_temp = None
            
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    area.tag_redraw()
        
        return {'FINISHED'}


class SCATTER_OT_confirm_add_ground(Operator):
    bl_idname = "scatter.confirm_add_ground"
    bl_label = "Add this object as ground"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        return {'CANCELLED'}


class SCATTER_OT_cancel_add_ground(Operator):
    bl_idname = "scatter.cancel_add_ground"
    bl_label = "Cancel"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        return {'CANCELLED'}


class SCATTER_OT_set_active_ground(Operator):
    bl_idname = "scatter.set_active_ground"
    bl_label = "Set active ground"
    bl_options = {'INTERNAL'}

    index: IntProperty()

    def execute(self, context):
        context.scene.active_ground_index = self.index
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
        
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        
        return {'FINISHED'}


classes = (
    SCATTER_OT_add_ground_popup,
    SCATTER_OT_confirm_add_ground,
    SCATTER_OT_cancel_add_ground,
    SCATTER_OT_set_active_ground,
    SCATTER_OT_delete_ground,
)