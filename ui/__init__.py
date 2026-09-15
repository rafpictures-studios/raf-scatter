import bpy

from . import lists
from . import menus
from . import panels

_modules = (
    lists,
    menus,
    panels,
)


def register():
    for mod in _modules:
        for cls in mod.classes:
            bpy.utils.register_class(cls)


def unregister():
    for mod in reversed(_modules):
        for cls in reversed(mod.classes):
            bpy.utils.unregister_class(cls)