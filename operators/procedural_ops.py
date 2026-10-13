from bpy.props import EnumProperty
from bpy.types import Operator

from ..properties import sync_system_auto_name
from ..utils import geonodes as geonodes_utils


_INSTANCES_SOURCE_ITEMS = (
    ('OBJECT', "Object", "Instance a single object"),
    ('COLLECTION', "Collection", "Instance a collection"),
)

_INSTANCES_SOURCE_INDEX = {
    'OBJECT': 0,
    'COLLECTION': 1,
}


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


class SCATTER_OT_toggle_procedural_instances(Operator):
    bl_idname = "scatter.toggle_procedural_instances"
    bl_label = "Use Instances"
    bl_description = "Add the procedural instances modifier"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        system = _get_active_system(context)
        if geonodes_utils.get_procedural_modifier(system) is None:
            return False
        return geonodes_utils.get_instances_modifier(system) is None

    def execute(self, context):
        system = _get_active_system(context)
        modifier = geonodes_utils.add_instances_modifier(system.curve_obj)
        geonodes_utils.apply_instances_assignment(system)
        geonodes_utils.randomize_seed(modifier)
        return {'FINISHED'}


class SCATTER_OT_set_instances_source(Operator):
    bl_idname = "scatter.set_instances_source"
    bl_label = "Set Instances Source"
    bl_description = "Switch between instancing a single object or a collection"
    bl_options = {'REGISTER', 'UNDO'}

    source: EnumProperty(items=_INSTANCES_SOURCE_ITEMS)

    @classmethod
    def poll(cls, context):
        system = _get_active_system(context)
        return geonodes_utils.get_instances_modifier(system) is not None

    def execute(self, context):
        system = _get_active_system(context)
        modifier = geonodes_utils.get_instances_modifier(system)
        if modifier is None:
            return {'CANCELLED'}
        index = _INSTANCES_SOURCE_INDEX[self.source]
        if not geonodes_utils.set_modifier_input_value(modifier, "Instances", index):
            self.report({'WARNING'}, "Instances socket not found")
            return {'CANCELLED'}
        system.instances_mode = index
        sync_system_auto_name(system)
        context.view_layer.update()
        return {'FINISHED'}


classes = (
    SCATTER_OT_toggle_procedural_instances,
    SCATTER_OT_set_instances_source,
)