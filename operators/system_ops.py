"""Operators for scatter system creation and management."""
import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator

from . import brush_ops
from ..utils import geonodes as geonodes_utils


SYSTEM_TYPE_ITEMS = (
    ('MANUAL', "Paint", "Paint points by hand using curve brushes", 'BRUSH_DATA', 0),
    ('PROCEDURAL', "Procedural", "Auto-distribute points on faces", 'MOD_PARTICLES', 1),
)
_SYSTEM_TYPE_NAME_PREFIX = {
    'MANUAL': "paintScatter",
    'PROCEDURAL': "proceduralScatter",
}


#----SYSTEM HELPERS----
def _tag_redraw_viewport(context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def _get_active_ground(context):
    """Return the active target ground or None."""
    scene = context.scene
    idx = scene.active_ground_index
    if not (0 <= idx < len(scene.scatter_grounds)):
        return None
    return scene.scatter_grounds[idx]


def _generate_system_name(ground, system_type):
    """Return the next unused default name for a system type."""
    prefix = _SYSTEM_TYPE_NAME_PREFIX[system_type]
    existing = {system.name for system in ground.scatter_systems}
    index = 1
    while f"{prefix}_{index:02d}" in existing:
        index += 1
    return f"{prefix}_{index:02d}"


def _ensure_target_uv(target):
    """Ensure a mesh target has UV layers, creating them if needed."""
    if target is None or target.type != 'MESH':
        return
    if target.data.uv_layers:
        return
    bpy.ops.object.mode_set(mode='EDIT')
    try:
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.smart_project()
    except RuntimeError:
        print(f"[RAF Scatter] Smart UV Project failed on '{target.name}' — continuing without UVs")
    bpy.ops.object.mode_set(mode='OBJECT')


def _exit_manual_brush_mode(context):
    """Close the paint session and leave sculpt mode if a scatter curve is sculpting."""
    scene = context.scene
    sculpting = any(
        system.curve_obj is not None and system.curve_obj.mode == 'SCULPT_CURVES'
        for ground in scene.scatter_grounds
        for system in ground.scatter_systems
    )
    if not sculpting:
        return
    brush_ops.end_paint_session(context)
    try:
        bpy.ops.object.mode_set(mode='OBJECT')
    except RuntimeError:
        pass


#----SYSTEM REMOVAL----
def remove_system_curve(context, curve_obj):
    """Delete a system's curve object with its effector modifiers and its curves data."""
    if curve_obj is None:
        return
    scene = context.scene
    if scene.scatter_paint_curve_obj == curve_obj:
        brush_ops.end_paint_session(context)
    if curve_obj.mode != 'OBJECT' and context.view_layer.objects.active == curve_obj:
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass
    curves_data = curve_obj.data
    bpy.data.objects.remove(curve_obj, do_unlink=True)
    if curves_data is not None and curves_data.users == 0:
        bpy.data.hair_curves.remove(curves_data)


#----SYSTEM CREATION----
def _move_to_ground_collections(curve_obj, ground_obj):
    """Put a system curve in the collections of its ground, where it is parented."""
    targets = list(ground_obj.users_collection)
    if not targets:
        return
    for collection in targets:
        if curve_obj.name not in collection.objects:
            collection.objects.link(curve_obj)
    for collection in list(curve_obj.users_collection):
        if collection not in targets:
            collection.objects.unlink(curve_obj)


def create_system(context, ground, system_type, name=None):
    """Add a scatter system with its curve and points stage at the top of the ground list."""
    target = ground.target_object
    _exit_manual_brush_mode(context)
    for obj in context.selected_objects:
        obj.select_set(False)
    target.select_set(True)
    context.view_layer.objects.active = target
    if system_type == 'MANUAL':
        _ensure_target_uv(target)
    bpy.ops.object.curves_empty_hair_add()
    curve_obj = context.active_object
    _move_to_ground_collections(curve_obj, target)
    curve_obj.name = name or _generate_system_name(ground, system_type)
    warning = None
    try:
        modifier = geonodes_utils.setup_system_modifier_stack(curve_obj, system_type, target)
    except RuntimeError as e:
        warning = str(e)
    else:
        if system_type == 'PROCEDURAL':
            geonodes_utils.randomize_seed(modifier)
    item = ground.scatter_systems.add()
    item.system_type = system_type
    item.target_ground = target
    item.curve_obj = curve_obj
    item.name = curve_obj.name
    ground.scatter_systems.move(len(ground.scatter_systems) - 1, 0)
    ground.active_scatter_system_index = 0
    return ground.scatter_systems[0], warning


#----OPERATORS----
class SCATTER_OT_add_system(Operator):
    bl_idname = "scatter.add_system"
    bl_label = "Add Scatter System"
    bl_description = "Add a scatter system of the chosen type to the active ground"
    bl_options = {'REGISTER', 'UNDO'}

    system_type: EnumProperty(items=SYSTEM_TYPE_ITEMS, default='MANUAL')

    @classmethod
    def poll(cls, context):
        return _get_active_ground(context) is not None

    def execute(self, context):
        ground = _get_active_ground(context)
        _system, warning = create_system(context, ground, self.system_type)
        if warning:
            self.report({'WARNING'}, warning)
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
        remove_system_curve(context, ground.scatter_systems[idx].curve_obj)
        ground.scatter_systems.remove(idx)
        ground.active_scatter_system_index = max(0, idx - 1)
        _tag_redraw_viewport(context)
        return {'FINISHED'}


class SCATTER_OT_duplicate_system(Operator):
    bl_idname = "scatter.duplicate_system"
    bl_label = "Duplicate system"
    bl_description = "Duplicate the active scatter system and its curve"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ground = _get_active_ground(context)
        if ground is None:
            return False
        return 0 <= ground.active_scatter_system_index < len(ground.scatter_systems)

    def execute(self, context):
        ground = _get_active_ground(context)
        system = ground.scatter_systems[ground.active_scatter_system_index]
        if system.curve_obj is None:
            return {'CANCELLED'}
        new_obj = geonodes_utils.duplicate_system_curve(system.curve_obj)
        new_system = ground.scatter_systems.add()
        new_system.system_type = system.system_type
        new_system.target_ground = system.target_ground
        new_system.curve_obj = new_obj
        new_system.instances_object = system.instances_object
        new_system.instances_collection = system.instances_collection
        new_system.instances_mode = system.instances_mode
        new_system.manual_instances_object = system.manual_instances_object
        new_system.manual_instances_collection = system.manual_instances_collection
        new_system.manual_instances_mode = system.manual_instances_mode
        for effector in system.effectors:
            new_effector = new_system.effectors.add()
            new_effector.effector_type = effector.effector_type
            new_effector.curve_obj = new_obj
            new_effector.modifier_name = effector.modifier_name
            new_effector.name = effector.name
            new_effector.vertex_mode = effector.vertex_mode
            new_effector.vertex_group_name = effector.vertex_group_name
            new_effector.proximity_object = effector.proximity_object
            new_effector.proximity_collection = effector.proximity_collection
        new_system.name = new_obj.name
        ground.scatter_systems.move(len(ground.scatter_systems) - 1, 0)
        ground.active_scatter_system_index = 0
        _tag_redraw_viewport(context)
        return {'FINISHED'}


class SCATTER_OT_toggle_curve_visibility(Operator):
    bl_idname = "scatter.toggle_curve_visibility"
    bl_label = "Toggle Curve Visibility"
    bl_description = (
        "Toggle viewport or render visibility of a scatter curve. Alt-click to isolate it"
    )
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(items=[
        ('VIEWPORT', "Viewport", "Toggle global viewport visibility"),
        ('RENDER', "Render", "Toggle global render visibility"),
    ])
    system_index: IntProperty(default=-1)
    isolate: BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        scene = context.scene
        return 0 <= scene.active_ground_index < len(scene.scatter_grounds)

    def invoke(self, context, event):
        self.isolate = event.alt
        return self.execute(context)

    def execute(self, context):
        scene = context.scene
        ground = scene.scatter_grounds[scene.active_ground_index]
        systems = ground.scatter_systems
        if not (0 <= self.system_index < len(systems)):
            return {'CANCELLED'}
        curve_obj = systems[self.system_index].curve_obj
        if curve_obj is None:
            return {'CANCELLED'}
        attr = 'hide_viewport' if self.mode == 'VIEWPORT' else 'hide_render'
        if not self.isolate:
            setattr(curve_obj, attr, not getattr(curve_obj, attr))
            return {'FINISHED'}
        if brush_ops.is_paint_session_active(scene):
            self.report({'WARNING'}, "Stop painting first")
            return {'CANCELLED'}
        others = [
            system.curve_obj for index, system in enumerate(systems)
            if index != self.system_index and system.curve_obj is not None
        ]
        isolated = not getattr(curve_obj, attr) and all(getattr(obj, attr) for obj in others)
        setattr(curve_obj, attr, False)
        for obj in others:
            setattr(obj, attr, not isolated)
        return {'FINISHED'}


class SCATTER_OT_randomize_seed(Operator):
    bl_idname = "scatter.randomize_seed"
    bl_label = "Random Seed"
    bl_description = "Roll a new random seed"
    bl_options = {'REGISTER', 'UNDO'}

    modifier_name: StringProperty(options={'HIDDEN'})
    socket_name: StringProperty(default="Seed", options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        ground = _get_active_ground(context)
        return ground is not None and 0 <= ground.active_scatter_system_index < len(
            ground.scatter_systems
        )

    def execute(self, context):
        ground = _get_active_ground(context)
        curve_obj = ground.scatter_systems[ground.active_scatter_system_index].curve_obj
        if curve_obj is None:
            return {'CANCELLED'}
        modifier = curve_obj.modifiers.get(self.modifier_name)
        if not geonodes_utils.randomize_seed(modifier, self.socket_name):
            self.report({'WARNING'}, "Seed socket not found")
            return {'CANCELLED'}
        return {'FINISHED'}


classes = (
    SCATTER_OT_add_system,
    SCATTER_OT_remove_system,
    SCATTER_OT_duplicate_system,
    SCATTER_OT_toggle_curve_visibility,
    SCATTER_OT_randomize_seed,
)