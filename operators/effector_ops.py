"""Operators for adding, editing, and configuring effectors."""
import time

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator

from ..properties import (
    EFFECTOR_TYPE_ITEMS, EFFECTOR_TYPE_LABELS, PROCEDURAL_ONLY_EFFECTORS, VERTEX_MASK_GROUP_PREFIX,
)
from ..utils import biomes as biomes_utils
from ..utils import geonodes as geonodes_utils


_DOUBLE_CLICK_SECONDS = 0.35
_last_click = (None, 0.0)


#----ACTIVE LOOKUP----
def _get_active_system(context):
    scene = context.scene
    g_idx = scene.active_ground_index
    if not (0 <= g_idx < len(scene.scatter_grounds)):
        return None
    ground = scene.scatter_grounds[g_idx]
    s_idx = ground.active_scatter_system_index
    if not (0 <= s_idx < len(ground.scatter_systems)):
        return None
    return ground.scatter_systems[s_idx]


def _get_active_effector(context):
    system = _get_active_system(context)
    if system is None:
        return None, None
    if not (0 <= system.active_effector_index < len(system.effectors)):
        return system, None
    return system, system.effectors[system.active_effector_index]


#----VIEWPORT REFRESH----
def _tag_redraw_viewport(context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def _force_scene_update(context):
    """Re-evaluate the depsgraph synchronously."""
    # some builds skip GN re-evaluation after IDProp socket writes even when tagged
    context.view_layer.update()


#----SOCKET WRITES----
def _assign_image_to_active_socket(context, image):
    system, effector = _get_active_effector(context)
    if system is None or effector is None:
        return False
    modifier = geonodes_utils.get_effector_modifier(system, effector)
    if modifier is None:
        return False
    return geonodes_utils.set_modifier_input_value(modifier, "Image", image)


#----EFFECTOR CREATION----
def create_effector(system, effector_type):
    """Add an effector and its modifier at the top of the stack, or return None."""
    effector = system.effectors.add()
    effector.effector_type = effector_type
    effector.curve_obj = system.curve_obj
    effector.name = EFFECTOR_TYPE_LABELS.get(effector_type, "Mask")
    modifier = geonodes_utils.append_effector_to_stack(
        system.curve_obj, effector_type, effector.name, system.target_ground
    )
    if modifier is None:
        system.effectors.remove(len(system.effectors) - 1)
        return None
    geonodes_utils.randomize_seed(modifier)
    effector.modifier_name = modifier.name
    if effector.name != modifier.name:
        effector.name = modifier.name
    system.effectors.move(len(system.effectors) - 1, 0)
    system.active_effector_index = 0
    return system.effectors[0]


class SCATTER_OT_add_effector(Operator):
    bl_idname = "scatter.add_effector"
    bl_label = "Add Mask"
    bl_description = "Add a mask to the active scatter system"
    bl_options = {'REGISTER', 'UNDO'}

    effector_type: EnumProperty(items=EFFECTOR_TYPE_ITEMS)

    @classmethod
    def poll(cls, context):
        return _get_active_system(context) is not None

    def execute(self, context):
        system = _get_active_system(context)
        if system is None or system.curve_obj is None:
            return {'CANCELLED'}
        if self.effector_type not in geonodes_utils.EFFECTOR_NODE_GROUPS:
            self.report({'ERROR'}, f"Mask type has no node group: {self.effector_type}")
            return {'CANCELLED'}
        if system.system_type == 'MANUAL' and self.effector_type in PROCEDURAL_ONLY_EFFECTORS:
            self.report({'WARNING'}, "This mask is only available for procedural systems")
            return {'CANCELLED'}
        if create_effector(system, self.effector_type) is None:
            self.report({'ERROR'}, f"No node group for mask type: {self.effector_type}")
            return {'CANCELLED'}
        _tag_redraw_viewport(context)
        return {'FINISHED'}


class SCATTER_OT_remove_effector(Operator):
    bl_idname = "scatter.remove_effector"
    bl_label = "Remove Mask"
    bl_description = "Remove the active mask"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        _system, effector = _get_active_effector(context)
        return effector is not None

    def execute(self, context):
        system = _get_active_system(context)
        effector = system.effectors[system.active_effector_index]
        geonodes_utils.remove_effector_modifier(system, effector)
        system.effectors.remove(system.active_effector_index)
        system.active_effector_index = max(0, system.active_effector_index - 1)
        _tag_redraw_viewport(context)
        return {'FINISHED'}


class SCATTER_OT_duplicate_effector(Operator):
    bl_idname = "scatter.duplicate_effector"
    bl_label = "Duplicate Mask"
    bl_description = "Duplicate the active mask"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        _system, effector = _get_active_effector(context)
        return effector is not None

    def execute(self, context):
        system = _get_active_system(context)
        if system.curve_obj is None:
            return {'CANCELLED'}
        effector = system.effectors[system.active_effector_index]
        modifier = geonodes_utils.get_effector_modifier(system, effector)
        if modifier is None:
            return {'CANCELLED'}
        new_modifier = geonodes_utils.duplicate_effector_modifier(system.curve_obj, modifier)
        new_item = system.effectors.add()
        new_item.effector_type = effector.effector_type
        new_item.curve_obj = system.curve_obj
        new_item.modifier_name = new_modifier.name
        new_item.name = new_modifier.name
        new_item.vertex_mode = effector.vertex_mode
        new_item.vertex_group_name = effector.vertex_group_name
        new_item.proximity_object = effector.proximity_object
        new_item.proximity_collection = effector.proximity_collection
        system.effectors.move(len(system.effectors) - 1, 0)
        system.active_effector_index = 0
        _tag_redraw_viewport(context)
        return {'FINISHED'}


#----EFFECTOR SELECTION----
class SCATTER_OT_select_effector(Operator):
    bl_idname = "scatter.select_effector"
    bl_label = "Select Mask"
    bl_description = (
        "Click to select. Shift or Ctrl-click to add to or remove from the selection. "
        "Double-click to rename"
    )
    bl_options = {'REGISTER', 'UNDO'}

    effector_index: IntProperty(default=-1, options={'HIDDEN'})
    extend: BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        system = _get_active_system(context)
        return system is not None and len(system.effectors) > 0

    def invoke(self, context, event):
        global _last_click
        system = _get_active_system(context)
        self.extend = event.shift or event.ctrl
        click = (system.as_pointer(), self.effector_index)
        now = time.monotonic()
        is_double = (
            not self.extend and _last_click[0] == click
            and now - _last_click[1] < _DOUBLE_CLICK_SECONDS
        )
        _last_click = (None, 0.0) if is_double else (click, now)
        if is_double:
            bpy.ops.scatter.rename_effector('INVOKE_DEFAULT', effector_index=self.effector_index)
            return {'FINISHED'}
        return self.execute(context)

    def execute(self, context):
        system = _get_active_system(context)
        if not (0 <= self.effector_index < len(system.effectors)):
            return {'CANCELLED'}
        previous = [effector.selected for effector in system.effectors]
        system.active_effector_index = self.effector_index
        if self.extend:
            for effector, was_selected in zip(system.effectors, previous):
                effector.selected = was_selected
            clicked = system.effectors[self.effector_index]
            clicked.selected = not previous[self.effector_index]
        return {'FINISHED'}


class SCATTER_OT_rename_effector(Operator):
    bl_idname = "scatter.rename_effector"
    bl_label = "Rename Mask"
    bl_description = "Rename the mask and its modifier"
    bl_options = {'REGISTER', 'UNDO'}

    effector_index: IntProperty(default=-1, options={'HIDDEN'})
    new_name: StringProperty(name="Name")

    def invoke(self, context, event):
        system = _get_active_system(context)
        if system is None or not (0 <= self.effector_index < len(system.effectors)):
            return {'CANCELLED'}
        self.new_name = system.effectors[self.effector_index].name
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "new_name")

    def execute(self, context):
        system = _get_active_system(context)
        if system is None or not (0 <= self.effector_index < len(system.effectors)):
            return {'CANCELLED'}
        if self.new_name.strip():
            system.effectors[self.effector_index].name = self.new_name.strip()
        return {'FINISHED'}


#----EFFECTOR CLIPBOARD----
def _selected_effectors(system):
    """Return the selected effectors in stack order, or the active one when none is selected."""
    picked = [effector for effector in system.effectors if effector.selected]
    if picked:
        return picked
    if 0 <= system.active_effector_index < len(system.effectors):
        return [system.effectors[system.active_effector_index]]
    return []


class SCATTER_OT_copy_effectors(Operator):
    bl_idname = "scatter.copy_effectors"
    bl_label = "Copy Selected Masks"
    bl_description = (
        "Copy the selected masks (Shift-click to select several) so they can be pasted "
        "into another scatter system of this file"
    )
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        system = _get_active_system(context)
        return system is not None and len(system.effectors) > 0

    def execute(self, context):
        system = _get_active_system(context)
        effectors = _selected_effectors(system)
        if not effectors:
            return {'CANCELLED'}
        context.scene.scatter_effector_clipboard = biomes_utils.make_effector_clipboard(
            system, effectors,
        )
        names = ", ".join(effector.name for effector in effectors)
        self.report({'INFO'}, f"Copied {len(effectors)} mask(s): {names}")
        return {'FINISHED'}


class SCATTER_OT_paste_effectors(Operator):
    bl_idname = "scatter.paste_effectors"
    bl_label = "Paste Masks"
    bl_description = "Add the copied masks on top of the active system's mask stack"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        system = _get_active_system(context)
        if system is None or system.curve_obj is None:
            return False
        return biomes_utils.read_effector_clipboard(context.scene.scatter_effector_clipboard) is not None

    @classmethod
    def description(cls, context, properties):
        clipboard = biomes_utils.read_effector_clipboard(context.scene.scatter_effector_clipboard)
        if clipboard is None:
            return f"{cls.bl_description}. Nothing copied in this file yet"
        names = ", ".join(entry.get("name", entry["type"]) for entry in clipboard["effectors"])
        return f"{cls.bl_description}.\nCopied from {clipboard.get('source', '?')}: {names}"

    def execute(self, context):
        scene = context.scene
        system = _get_active_system(context)
        clipboard = biomes_utils.read_effector_clipboard(scene.scatter_effector_clipboard)
        if clipboard is None:
            self.report({'WARNING'}, "Nothing copied in this file yet")
            return {'CANCELLED'}
        added = 0
        skipped = []
        unresolved = []
        for entry in reversed(clipboard["effectors"]):
            effector_type = entry["type"]
            label = EFFECTOR_TYPE_LABELS.get(effector_type, effector_type)
            if system.system_type == 'MANUAL' and effector_type in PROCEDURAL_ONLY_EFFECTORS:
                skipped.append(label)
                continue
            effector = create_effector(system, effector_type)
            if effector is None:
                skipped.append(label)
                continue
            unresolved += biomes_utils.apply_effector_entry(system, effector, entry, scene)
            added += 1
        system.active_effector_index = 0
        _force_scene_update(context)
        _tag_redraw_viewport(context)
        message = f"Pasted {added} mask(s)"
        if skipped:
            message += f"; skipped: {', '.join(skipped)}"
        if unresolved:
            message += f"; left empty: {', '.join(unresolved)}"
        self.report({'WARNING'} if skipped or unresolved else {'INFO'}, message)
        return {'FINISHED'} if added else {'CANCELLED'}


class SCATTER_OT_toggle_effector_visibility(Operator):
    bl_idname = "scatter.toggle_effector_visibility"
    bl_label = "Toggle Mask Visibility"
    bl_description = (
        "Toggle the viewport or render visibility of the mask. Alt-click to isolate it"
    )
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(
        items=[
            ('VIEWPORT', "Viewport", "Toggle viewport visibility"),
            ('RENDER', "Render", "Toggle render visibility"),
        ],
    )
    effector_index: IntProperty(default=-1)
    isolate: BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        system = _get_active_system(context)
        return system is not None and len(system.effectors) > 0

    def invoke(self, context, event):
        self.isolate = event.alt
        return self.execute(context)

    def execute(self, context):
        system = _get_active_system(context)
        if system is None:
            return {'CANCELLED'}
        if not (0 <= self.effector_index < len(system.effectors)):
            return {'CANCELLED'}
        modifier = geonodes_utils.get_effector_modifier(system, system.effectors[self.effector_index])
        if modifier is None:
            return {'CANCELLED'}
        attr = 'show_viewport' if self.mode == 'VIEWPORT' else 'show_render'
        if not self.isolate:
            setattr(modifier, attr, not getattr(modifier, attr))
            return {'FINISHED'}
        others = [
            geonodes_utils.get_effector_modifier(system, effector)
            for index, effector in enumerate(system.effectors) if index != self.effector_index
        ]
        others = [other for other in others if other is not None]
        isolated = getattr(modifier, attr) and not any(getattr(other, attr) for other in others)
        setattr(modifier, attr, True)
        for other in others:
            setattr(other, attr, isolated)
        return {'FINISHED'}


class SCATTER_OT_set_texture_option(Operator):
    bl_idname = "scatter.set_texture_option"
    bl_label = "Set Texture"
    bl_description = "Choose the texture type used by the mask"
    bl_options = {'REGISTER', 'UNDO'}

    option: EnumProperty(
        items=[(name.upper(), name, "") for name, _sockets in geonodes_utils.TEXTURE_MENU_OPTIONS]
    )

    @classmethod
    def poll(cls, context):
        _system, effector = _get_active_effector(context)
        return effector is not None and effector.effector_type == 'MASK_BY_TEXTURE'

    def execute(self, context):
        system, effector = _get_active_effector(context)
        if system is None or effector is None:
            return {'CANCELLED'}
        modifier = geonodes_utils.get_effector_modifier(system, effector)
        if modifier is None:
            return {'CANCELLED'}
        option_name = next(
            name for name, _sockets in geonodes_utils.TEXTURE_MENU_OPTIONS
            if name.upper() == self.option
        )
        option_value = geonodes_utils.get_menu_socket_items(modifier, "Texture").get(option_name)
        if option_value is None:
            self.report({'WARNING'}, f"Texture menu has no \"{option_name}\" item")
            return {'CANCELLED'}
        if not geonodes_utils.set_modifier_input_value(modifier, "Texture", option_value):
            self.report({'WARNING'}, "Texture socket not found")
            return {'CANCELLED'}
        _force_scene_update(context)
        return {'FINISHED'}


class SCATTER_OT_set_proximity_target(Operator):
    bl_idname = "scatter.set_proximity_target"
    bl_label = "Set Proximity Target"
    bl_description = "Choose whether the proximity target is an object or a collection"
    bl_options = {'REGISTER', 'UNDO'}

    source: EnumProperty(
        items=[
            ('OBJECT', "Object", "Target a single object"),
            ('COLLECTION', "Collection", "Target a collection"),
        ],
    )

    @classmethod
    def poll(cls, context):
        _system, effector = _get_active_effector(context)
        return effector is not None and effector.effector_type == 'GEOMETRY_PROXIMITY'

    def execute(self, context):
        system, effector = _get_active_effector(context)
        if system is None or effector is None:
            return {'CANCELLED'}
        modifier = geonodes_utils.get_effector_modifier(system, effector)
        if modifier is None:
            return {'CANCELLED'}
        index = 0 if self.source == 'OBJECT' else 1
        if not geonodes_utils.set_modifier_input_value(modifier, "Target", index):
            self.report({'WARNING'}, "Target socket not found")
            return {'CANCELLED'}
        _force_scene_update(context)
        return {'FINISHED'}


class SCATTER_OT_set_vertex_mode(Operator):
    bl_idname = "scatter.set_vertex_mode"
    bl_label = "Set Vertex Mask Source"
    bl_description = "Choose between painting a new vertex group and using an existing one"
    bl_options = {'REGISTER', 'UNDO'}

    source: EnumProperty(
        items=[
            ('PAINT', "Paint New", "Create a fresh group and weight paint it"),
            ('EXISTING', "Existing Group", "Pick a vertex group already on the ground"),
        ],
    )

    @classmethod
    def poll(cls, context):
        _system, effector = _get_active_effector(context)
        return effector is not None and effector.effector_type == 'MASK_BY_ATTRIBUTE'

    def execute(self, context):
        system, effector = _get_active_effector(context)
        if system is None or effector is None:
            return {'CANCELLED'}
        effector.vertex_mode = 0 if self.source == 'PAINT' else 1
        return {'FINISHED'}


class SCATTER_OT_toggle_edge_blend(Operator):
    bl_idname = "scatter.toggle_edge_blend"
    bl_label = "Toggle Edge Blend"
    bl_description = "Toggle the edge blend treatment of the mask"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        _system, effector = _get_active_effector(context)
        return effector is not None and effector.effector_type in (
            'MASK_BY_POSITION', 'MASK_BY_NORMAL', 'GEOMETRY_PROXIMITY', 'MASK_BY_ATTRIBUTE',
        )

    def execute(self, context):
        system, effector = _get_active_effector(context)
        if system is None or effector is None:
            return {'CANCELLED'}
        modifier = geonodes_utils.get_effector_modifier(system, effector)
        if modifier is None:
            return {'CANCELLED'}
        current = bool(geonodes_utils.get_modifier_input_value(modifier, "Edge Blend", False))
        if not geonodes_utils.set_modifier_input_value(modifier, "Edge Blend", not current):
            self.report({'WARNING'}, "Edge Blend socket not found")
            return {'CANCELLED'}
        _force_scene_update(context)
        return {'FINISHED'}


class SCATTER_OT_start_vertex_paint(Operator):
    bl_idname = "scatter.start_vertex_paint"
    bl_label = "Start Paint"
    bl_description = (
        "Enter Weight Paint mode on the ground object with the mask vertex group active"
    )
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        _system, effector = _get_active_effector(context)
        return effector is not None and effector.effector_type == 'MASK_BY_ATTRIBUTE'

    def execute(self, context):
        system, effector = _get_active_effector(context)
        ground = system.target_ground
        if ground is None or ground.type != 'MESH':
            self.report({'ERROR'}, "Active system has no mesh Target Ground")
            return {'CANCELLED'}
        if ground.mode == 'WEIGHT_PAINT':
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'FINISHED'}
        group_name = VERTEX_MASK_GROUP_PREFIX + ground.name
        group = ground.vertex_groups.get(group_name)
        if group is None:
            group = ground.vertex_groups.new(name=group_name)
        # 'active' lives on the vertex_groups collection, not on each VertexGroup
        ground.vertex_groups.active = group
        if ground.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for obj in context.selected_objects:
            obj.select_set(False)
        ground.select_set(True)
        context.view_layer.objects.active = ground
        bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
        effector.vertex_mode = 0
        effector.vertex_group_name = group_name
        return {'FINISHED'}


class SCATTER_OT_open_mask_image(Operator):
    bl_idname = "scatter.open_mask_image"
    bl_label = "Open Image"
    bl_description = "Load an image file for the texture mask"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.exr;*.bmp;*.tga;*.webp")

    @classmethod
    def poll(cls, context):
        _system, effector = _get_active_effector(context)
        return effector is not None and effector.effector_type == 'MASK_BY_TEXTURE'

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            image = bpy.data.images.load(self.filepath, check_existing=True)
        except RuntimeError:
            self.report({'ERROR'}, "Could not load image file")
            return {'CANCELLED'}
        if not _assign_image_to_active_socket(context, image):
            self.report({'WARNING'}, "Active mask has no Image socket")
            return {'CANCELLED'}
        _force_scene_update(context)
        _tag_redraw_viewport(context)
        return {'FINISHED'}


classes = (
    SCATTER_OT_add_effector,
    SCATTER_OT_remove_effector,
    SCATTER_OT_duplicate_effector,
    SCATTER_OT_select_effector,
    SCATTER_OT_rename_effector,
    SCATTER_OT_copy_effectors,
    SCATTER_OT_paste_effectors,
    SCATTER_OT_toggle_effector_visibility,
    SCATTER_OT_set_texture_option,
    SCATTER_OT_set_proximity_target,
    SCATTER_OT_set_vertex_mode,
    SCATTER_OT_toggle_edge_blend,
    SCATTER_OT_start_vertex_paint,
    SCATTER_OT_open_mask_image,
)