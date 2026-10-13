import bpy

from . import ground_ops
from . import system_ops
from . import effector_ops
from . import brush_ops
from . import procedural_ops
from . import manual_ops
from . import library_ops
from . import biome_ops
from . import pack_ops

_modules = (
    ground_ops,
    system_ops,
    effector_ops,
    brush_ops,
    procedural_ops,
    manual_ops,
    library_ops,
    biome_ops,
    pack_ops,
)


def register():
    for mod in _modules:
        for cls in mod.classes:
            bpy.utils.register_class(cls)
        if hasattr(mod, "register"):
            mod.register()


def unregister():
    for mod in reversed(_modules):
        if hasattr(mod, "unregister"):
            mod.unregister()
        for cls in reversed(mod.classes):
            bpy.utils.unregister_class(cls)