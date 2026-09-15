from bpy.types import Operator

from ..utils import geonodes as geonodes_utils


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


class SCATTER_OT_regenerate_procedural(Operator):
    bl_idname = "scatter.regenerate_procedural"
    bl_label = "Regenerate procedural distribution"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        system = _get_active_system(context)
        return geonodes_utils.get_procedural_modifier(system) is not None

    def execute(self, context):
        system = _get_active_system(context)
        modifier = geonodes_utils.get_procedural_modifier(system)
        current_seed = geonodes_utils.get_modifier_input_value(modifier, "Seed", 0)

        try:
            next_seed = int(current_seed) + 1
        except (TypeError, ValueError):
            next_seed = 1

        if not geonodes_utils.set_modifier_input_value(modifier, "Seed", next_seed):
            self.report({'WARNING'}, "Seed socket not found")
            return {'CANCELLED'}

        return {'FINISHED'}


class SCATTER_OT_toggle_procedural_instances(Operator):
    """Toggles the gn_proceduralScatter_instances modifier on/off for
    the active procedural system. The node group is already linked at
    system-creation time (setup_system_modifier_stack()), so this only
    ever creates/removes the modifier — no library load here."""
    bl_idname = "scatter.toggle_procedural_instances"
    bl_label = "Toggle Use Instances"
    bl_description = "Add or remove the Instances modifier on the active procedural system"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        system = _get_active_system(context)
        return geonodes_utils.get_procedural_modifier(system) is not None

    def execute(self, context):
        system = _get_active_system(context)
        curve_obj = system.curve_obj

        if geonodes_utils.get_instances_modifier(system) is not None:
            geonodes_utils.remove_instances_modifier(curve_obj)
        else:
            geonodes_utils.add_instances_modifier(curve_obj)

        return {'FINISHED'}


classes = (
    SCATTER_OT_regenerate_procedural,
    SCATTER_OT_toggle_procedural_instances,
)