from bpy.types import Operator
from bpy.props import EnumProperty


BRUSH_ITEMS = [
    ('ADD', "Add", ""),
    ('DENSITY', "Density", ""),
    ('DELETE', "Delete", ""),
    ('SLIDE', "Slide", ""),
]

BRUSH_ICONS = {
    'ADD': 'ADD',
    'DENSITY': 'STICKY_UVS_LOC',
    'DELETE': 'TRASH',
    'SLIDE': 'ARROW_LEFTRIGHT',
}

BRUSH_TOOLTIPS = {
    'ADD': "Add — place new points on the target surface",
    'DENSITY': "Density — increase or decrease point density locally",
    'DELETE': "Delete — remove points within the brush area",
    'SLIDE': "Slide — slide points along the target surface",
}


class SCATTER_OT_toggle_manual_mode(Operator):
    bl_idname = "scatter.toggle_manual_mode"
    bl_label = "Toggle manual scatter mode"

    def execute(self, context):
        scene = context.scene
        scene.scatter_manual_mode_on = not scene.scatter_manual_mode_on


        return {'FINISHED'}


class SCATTER_OT_set_brush(Operator):
    bl_idname = "scatter.set_brush"
    bl_label = "Set active brush"
    bl_options = {'INTERNAL'}

    brush: EnumProperty(items=BRUSH_ITEMS)

    @classmethod
    def description(cls, context, properties):
        return BRUSH_TOOLTIPS.get(properties.brush, "")

    def execute(self, context):
        context.scene.scatter_active_brush = self.brush
        return {'FINISHED'}


classes = (
    SCATTER_OT_toggle_manual_mode,
    SCATTER_OT_set_brush,
)
