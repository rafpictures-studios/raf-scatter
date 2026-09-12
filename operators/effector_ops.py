from bpy.types import Operator
from bpy.props import EnumProperty


def _get_active_system(context):
    scene = context.scene
    g_idx = scene.active_ground_index
    if not (0 <= g_idx < len(scene.scatter_grounds)):
        return None
    ground = scene.scatter_grounds[g_idx]
    s_idx = ground.active_scatter_system_index
    if not (0 <= s_idx < len(ground.scatter_systems)):
        return None
    return ground.scatter_systems[s_idx]


class SCATTER_OT_add_effector(Operator):
    bl_idname = "scatter.add_effector"
    bl_label = "Add effector"

    @classmethod
    def poll(cls, context):
        return _get_active_system(context) is not None

    def execute(self, context):
        system = _get_active_system(context)
        effector = system.effectors.add()
        effector.name = f"Effector {len(system.effectors)}"
        return {'FINISHED'}


class SCATTER_OT_remove_effector(Operator):
    bl_idname = "scatter.remove_effector"
    bl_label = "Remove effector"

    @classmethod
    def poll(cls, context):
        system = _get_active_system(context)
        if system is None:
            return False
        return 0 <= system.active_effector_index < len(system.effectors)

    def execute(self, context):
        system = _get_active_system(context)
        system.effectors.remove(system.active_effector_index)
        system.active_effector_index = max(0, system.active_effector_index - 1)
        return {'FINISHED'}


class SCATTER_OT_move_effector(Operator):
    bl_idname = "scatter.move_effector"
    bl_label = "Move effector"

    direction: EnumProperty(
        items=[('UP', "Up", ""), ('DOWN', "Down", "")],
        default='UP',
    )

    @classmethod
    def poll(cls, context):
        system = _get_active_system(context)
        if system is None:
            return False
        return 0 <= system.active_effector_index < len(system.effectors)

    def execute(self, context):
        system = _get_active_system(context)
        idx = system.active_effector_index
        new_idx = idx - 1 if self.direction == 'UP' else idx + 1

        if not (0 <= new_idx < len(system.effectors)):
            return {'CANCELLED'}

        system.effectors.move(idx, new_idx)
        system.active_effector_index = new_idx
        return {'FINISHED'}


classes = (
    SCATTER_OT_add_effector,
    SCATTER_OT_remove_effector,
    SCATTER_OT_move_effector,
)