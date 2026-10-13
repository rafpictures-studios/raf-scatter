import bpy

from . import lists
from . import menus
from . import panels
from . import toolbar

_modules = (
    lists,
    menus,
    panels,
    toolbar,
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
