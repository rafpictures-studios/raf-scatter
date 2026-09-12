from bpy.types import Menu


class SCATTER_MT_add_system(Menu):
    bl_idname = "SCATTER_MT_add_system"
    bl_label = "Add scatter system"

    def draw(self, context):
        layout = self.layout
        op = layout.operator("scatter.add_system", text="Manual", icon='BRUSH_DATA')
        op.system_type = 'MANUAL'
        op = layout.operator("scatter.add_system", text="Procedural", icon='MOD_PARTICLES')
        op.system_type = 'PROCEDURAL'


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


classes = (
    SCATTER_MT_add_system,
    SCATTER_MT_grounds,
)