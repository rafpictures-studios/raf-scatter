import bpy
from bpy.types import Operator
from bpy.props import EnumProperty

from ..utils import geonodes as geonodes_utils


def _get_active_ground(context):
    scene = context.scene
    idx = scene.active_ground_index
    if not (0 <= idx < len(scene.scatter_grounds)):
        return None
    return scene.scatter_grounds[idx]


def _tag_redraw_viewport(context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


SYSTEM_TYPE_ITEMS = (
    ('MANUAL', "Manual", "Sculpt points by hand using curve brushes", 'BRUSH_DATA', 0),
    ('PROCEDURAL', "Procedural", "Auto-distribute points on faces", 'MOD_PARTICLES', 1),
)

_SYSTEM_TYPE_NAME_PREFIX = {
    'MANUAL': "scatterManual",
    'PROCEDURAL': "scatterProcedural",
}


def _generate_system_name(ground, system_type):
    """Default naming per type: scatterManual_01, scatterProcedural_01,
    etc. Finds the smallest unused two-digit index within this ground's
    own system list, so a deleted-then-recreated system reuses its slot
    instead of drifting upward like Blender's own .001 suffixing."""
    prefix = _SYSTEM_TYPE_NAME_PREFIX[system_type]
    existing = {system.name for system in ground.scatter_systems}

    index = 1
    while f"{prefix}_{index:02d}" in existing:
        index += 1
    return f"{prefix}_{index:02d}"


class SCATTER_OT_add_system(Operator):
    """Adds a scatter system of the given type directly — invoked from
    SCATTER_MT_add_system_type (ui/menus.py). No dialog: the dropdown
    menu itself is the picker (Rule C: system_type is locked once set).

    NOTE (unverified, needs testing): the Curves object is now created
    via bpy.ops.object.curves_empty_hair_add() instead of manual
    bpy.data.curves.new(), so it's properly surface-bound from the
    start. This requires target to be the sole active/selected object
    at call time — handled below by forcing selection before the
    operator call."""
    bl_idname = "scatter.add_system"
    bl_label = "Add Scatter System"
    bl_options = {'REGISTER', 'UNDO'}

    system_type: EnumProperty(items=SYSTEM_TYPE_ITEMS, default='MANUAL')

    @classmethod
    def poll(cls, context):
        return _get_active_ground(context) is not None

    def execute(self, context):
        ground = _get_active_ground(context)
        target = ground.target_object

        for obj in context.selected_objects:
            obj.select_set(False)
        target.select_set(True)
        context.view_layer.objects.active = target

        bpy.ops.object.curves_empty_hair_add()
        curve_obj = context.active_object
        curve_obj.name = _generate_system_name(ground, self.system_type)

        try:
            geonodes_utils.setup_system_modifier_stack(curve_obj, self.system_type, target)
        except RuntimeError as e:
            self.report({'WARNING'}, str(e))

        item = ground.scatter_systems.add()
        item.system_type = self.system_type
        item.target_ground = target
        item.curve_obj = curve_obj
        item.name = curve_obj.name  

        ground.scatter_systems.move(len(ground.scatter_systems) - 1, 0)
        ground.active_scatter_system_index = 0

        _tag_redraw_viewport(context)
        return {'FINISHED'}


class SCATTER_OT_remove_system(Operator):
    bl_idname = "scatter.remove_system"
    bl_label = "Remove scatter system"
    bl_description = "Delete the active scatter system and its curve object"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ground = _get_active_ground(context)
        if ground is None:
            return False
        return 0 <= ground.active_scatter_system_index < len(ground.scatter_systems)

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        ground = _get_active_ground(context)
        idx = ground.active_scatter_system_index
        item = ground.scatter_systems[idx]

        if item.curve_obj:
            bpy.data.objects.remove(item.curve_obj, do_unlink=True)

        ground.scatter_systems.remove(idx)
        ground.active_scatter_system_index = max(0, idx - 1)

        _tag_redraw_viewport(context)
        return {'FINISHED'}


classes = (
    SCATTER_OT_add_system,
    SCATTER_OT_remove_system,
)