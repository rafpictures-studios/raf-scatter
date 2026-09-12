"""
utils/geonodes.py — Helper functions for reading/setting up Geometry
Nodes.

This is where all node_tree modifier stack logic will live (guide
section 5, "What is PLACEHOLDER"):
- Actual GeoNodes modifier stack generation on the Curves object.
- Appending Effector node groups from resources/node_groups.blend (linked).
- Reading node_tree.interface.items_tree (Blender 4.0+ API) to generate
  dynamic sliders in ui/panels.py, replacing the hardcoded
  density/scale_variance in properties.py.
- Procedural distribute-on-faces logic and seed manipulation.

All functions below are stubs — none are called from operators/ yet
until the GeoNodes implementation lands.
"""


def get_effector_node_group(effector_name):
    """TODO: return the node group linked from resources/node_groups.blend
    matching the given effector name."""
    raise NotImplementedError


def read_node_group_inputs(node_group):
    """TODO: read node_group.interface.items_tree and return a list of
    input sockets (name, type, default, min, max) to generate dynamic
    sliders in ui/panels.py draw_effectors()."""
    raise NotImplementedError


def append_effector_to_stack(curve_obj, effector_name):
    """TODO: append a new modifier to curve_obj using the effector_name
    node group, placed at the position matching its index in the stack
    (Rule B: bottom-to-top)."""
    raise NotImplementedError


def setup_system_modifier_stack(curve_obj, system_type):
    """TODO: set up the initial geonode modifier template on curve_obj
    matching system_type ('MANUAL' or 'PROCEDURAL'), linked from
    resources/node_groups.blend. Called from
    operators/system_ops.py::SCATTER_OT_add_system."""
    raise NotImplementedError
