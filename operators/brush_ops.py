from bpy.types import Operator


class SCATTER_OT_toggle_manual_mode(Operator):
    bl_idname = "scatter.toggle_manual_mode"
    bl_label = "Toggle manual scatter mode"

    def execute(self, context):
        scene = context.scene
        scene.scatter_manual_mode_on = not scene.scatter_manual_mode_on
        return {'FINISHED'}


classes = (
    SCATTER_OT_toggle_manual_mode,
)