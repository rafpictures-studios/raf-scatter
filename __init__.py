bl_info = {
    "name": "RAF Scatter",
    "description": "Ecosystem scattering toolkit for Blender.",
    "author": "Rizki Alfajri",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > N-panel > Scatter",
    "category": "Object",
}

from . import properties
from . import operators
from . import ui
from .utils import icons as icon_utils

_submodules = (
    properties,
    operators,
    ui,
    icon_utils,
)


def register():
    for mod in _submodules:
        mod.register()


def unregister():
    for mod in reversed(_submodules):
        mod.unregister()


if __name__ == "__main__":
    register()