from bpy.types import Operator


class SCATTER_OT_regenerate_procedural(Operator):
    bl_idname = "scatter.regenerate_procedural"
    bl_label = "Regenerate procedural distribution"

    def execute(self, context):
        return {'FINISHED'}


classes = (
    SCATTER_OT_regenerate_procedural,
)
