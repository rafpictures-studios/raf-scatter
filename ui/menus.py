from bpy.types import Menu

from ..operators.system_ops import SYSTEM_TYPE_ITEMS


class SCATTER_MT_grounds(Menu):
    bl_idname = "SCATTER_MT_grounds"
    bl_label = "Grounds"

    def draw(self, context):
        layout = self.layout
        active_idx = context.scene.active_ground_index
        for index, ground in enumerate(context.scene.scatter_grounds):
            icon = 'RADIOBUT_ON' if index == active_idx else 'RADIOBUT_OFF'
            op = layout.operator("scatter.set_active_ground", text=ground.name, icon=icon)
            op.index = index


class SCATTER_MT_add_system_type(Menu):
    bl_idname = "SCATTER_MT_add_system_type"
    bl_label = "Add Scatter System"

    def draw(self, context):
        layout = self.layout
        for identifier, name, description, icon, index in SYSTEM_TYPE_ITEMS:
            op = layout.operator("scatter.add_system", text=name, icon=icon)
            op.system_type = identifier


classes = (
    SCATTER_MT_grounds,
    SCATTER_MT_add_system_type,
)