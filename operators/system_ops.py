import bpy
from bpy.types import Operator
from bpy.props import EnumProperty


def _get_active_ground(context):
    scene = context.scene
    idx = scene.active_ground_index
    if not (0 <= idx < len(scene.scatter_grounds)):
        return None
    return scene.scatter_grounds[idx]


class SCATTER_OT_add_system(Operator):
    bl_idname = "scatter.add_system"
    bl_label = "Add scatter system"

    system_type: EnumProperty(
        items=[('MANUAL', "Manual", ""), ('PROCEDURAL', "Procedural", "")],
        default='MANUAL',
    )

    @classmethod
    def poll(cls, context):
        return _get_active_ground(context) is not None

    def execute(self, context):
        ground = _get_active_ground(context)
        target = ground.target_object

        curve_data = bpy.data.curves.new(name="ScatterCurveData", type='CURVE')
        curve_data.dimensions = '3D'
        curve_obj = bpy.data.objects.new(name=f"ScatterCurve_{target.name}", object_data=curve_data)
        context.collection.objects.link(curve_obj)

        item = ground.scatter_systems.add()
        item.name = curve_obj.name
        item.system_type = self.system_type
        item.target_ground = target
        item.curve_obj = curve_obj

        ground.scatter_systems.move(len(ground.scatter_systems) - 1, 0)
        ground.active_scatter_system_index = 0
        return {'FINISHED'}


class SCATTER_OT_remove_system(Operator):
    bl_idname = "scatter.remove_system"
    bl_label = "Remove scatter system"

    @classmethod
    def poll(cls, context):
        ground = _get_active_ground(context)
        if ground is None:
            return False
        return 0 <= ground.active_scatter_system_index < len(ground.scatter_systems)

    def execute(self, context):
        ground = _get_active_ground(context)
        idx = ground.active_scatter_system_index
        item = ground.scatter_systems[idx]

        if item.curve_obj:
            bpy.data.objects.remove(item.curve_obj, do_unlink=True)

        ground.scatter_systems.remove(idx)
        ground.active_scatter_system_index = max(0, idx - 1)
        return {'FINISHED'}


classes = (
    SCATTER_OT_add_system,
    SCATTER_OT_remove_system,
)