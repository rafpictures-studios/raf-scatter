import bpy
from bpy.props import (
    StringProperty, BoolProperty, FloatProperty, EnumProperty,
    PointerProperty, CollectionProperty, IntProperty,
)
from bpy.types import PropertyGroup


def _mesh_only_poll(self, obj):
    return obj.type == 'MESH'


class SCATTER_EffectorItem(PropertyGroup):
    name: StringProperty(name="Effector name", default="Effector")

    density: FloatProperty(name="Density", default=0.5, min=0.0, max=1.0)
    scale_variance: FloatProperty(name="Scale variance", default=0.3, min=0.0, max=1.0)


class SCATTER_SystemItem(PropertyGroup):
    name: StringProperty(name="System name", default="ScatterSystem")

    system_type: EnumProperty(
        name="Type",
        items=[
            ('MANUAL', "Manual", "Points placed manually via curve sculpting"),
            ('PROCEDURAL', "Procedural", "Points generated automatically (distribute on faces)"),
        ],
        default='MANUAL',
    )

    target_ground: PointerProperty(name="Target ground", type=bpy.types.Object)
    curve_obj: PointerProperty(name="Curve object", type=bpy.types.Object)

    effectors: CollectionProperty(type=SCATTER_EffectorItem)
    active_effector_index: IntProperty(default=0)


class SCATTER_GroundItem(PropertyGroup):
    """One target ground, with its own independent scatter system stack."""
    name: StringProperty(name="Ground name", default="Ground")

    target_object: PointerProperty(name="Target object", type=bpy.types.Object)

    scatter_systems: CollectionProperty(type=SCATTER_SystemItem)
    active_scatter_system_index: IntProperty(default=0)


classes = (
    SCATTER_EffectorItem,
    SCATTER_SystemItem,
    SCATTER_GroundItem,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.scatter_grounds = CollectionProperty(type=SCATTER_GroundItem)
    bpy.types.Scene.active_ground_index = IntProperty(default=0)
    bpy.types.Scene.scatter_ground_picker_temp = PointerProperty(
        name="Target ground",
        type=bpy.types.Object,
        poll=_mesh_only_poll,
    )

    bpy.types.Scene.scatter_manual_mode_on = BoolProperty(default=False)
    bpy.types.Scene.scatter_active_brush = EnumProperty(
        items=[
            ('ADD', "Add", ""),
            ('DENSITY', "Density", ""),
            ('DELETE', "Delete", ""),
            ('SLIDE', "Slide", ""),
        ],
        default='ADD',
    )
    bpy.types.Scene.scatter_procedural_seed = IntProperty(default=0)


def unregister():
    del bpy.types.Scene.scatter_procedural_seed
    del bpy.types.Scene.scatter_active_brush
    del bpy.types.Scene.scatter_manual_mode_on
    del bpy.types.Scene.scatter_ground_picker_temp
    del bpy.types.Scene.active_ground_index
    del bpy.types.Scene.scatter_grounds

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)