import bpy

from . import ground_ops
from . import system_ops
from . import effector_ops
from . import brush_ops
from . import procedural_ops

_modules = (
    ground_ops,
    system_ops,
    effector_ops,
    brush_ops,
    procedural_ops,
)


def register():
    for mod in _modules:
        for cls in mod.classes:
            bpy.utils.register_class(cls)


def unregister():
    for mod in reversed(_modules):
        for cls in reversed(mod.classes):
            bpy.utils.unregister_class(cls)