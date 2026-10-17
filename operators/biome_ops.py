"""Biome library state and operators for browsing, saving, loading and managing biomes."""
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator, PropertyGroup

from . import library_ops
from .effector_ops import create_effector
from .system_ops import create_system
from ..preferences import (
    BIOME_GROUP_IMPORTED, BIOME_GROUP_LOCAL, get_addon_prefs, is_biome_in_group,
    sync_biome_selection,
)
from ..properties import EFFECTOR_TYPE_LABELS, PROCEDURAL_ONLY_EFFECTORS, is_pickable_mesh
from ..utils import biomes as biomes_utils
from ..utils import geonodes as geonodes_utils
from ..utils import icons as icon_utils
from ..utils import packs as packs_utils


_ADDON_ID = __package__.split(".")[0]
_BROWSER_WIDTH = 320
_THUMBNAIL_SCALE = 6.0
_PREVIEW_FILTER = "*.png;*.jpg;*.jpeg"
_biome_pick_cache = []


#----ACTIVE LOOKUP----
def _get_active_ground(context):
    scene = context.scene
    idx = scene.active_ground_index
    if not (0 <= idx < len(scene.scatter_grounds)):
        return None
    return scene.scatter_grounds[idx]


#----BIOME LIBRARY----
def _refresh_packs(wm, packs):
    wm.scatter_packs.clear()
    for pack in packs:
        item = wm.scatter_packs.add()
        item.name = pack["id"]
        item.title = pack["name"]
        item.version = pack["version"]
        item.author = pack["author"]
        item.biome_count = len(pack["biomes"])
        item.asset_library = pack["asset_library"]
        item.valid = pack["valid"]

def refresh_biome_library(context=None, select=None):
    """Rescan saved biomes and installed packs into the thumbnails and window-manager lists."""
    context = context or bpy.context
    wm = context.window_manager
    packs = packs_utils.list_packs()
    entries = [(key, thumbnail, None) for key, thumbnail in biomes_utils.list_biomes()]
    for pack in packs:
        entries += [(key, thumbnail, pack) for key, thumbnail in pack["biomes"]]
    icon_utils.reload_biome_previews([(key, thumbnail) for key, thumbnail, _pack in entries])
    included = {item.name for item in wm.scatter_biomes if item.pack_include}
    items = wm.scatter_biomes
    items.clear()
    for key, _thumbnail, pack in entries:
        info = biomes_utils.read_biome_info(key)
        item = items.add()
        item.name = key
        item.label = biomes_utils.split_biome_key(key)[1]
        item.pack_id = pack["id"] if pack else ""
        item.pack_name = pack["name"] if pack else ""
        item.pack_include = key in included
        item.description = info["description"]
        item.created = info["created"]
        item.modified = info["modified"]
        item.manual_count = info["manual"]
        item.procedural_count = info["procedural"]
        item.file_path = info["file_path"]
        item.valid = info["valid"]
    _refresh_packs(wm, packs)
    keys = [key for key, _thumbnail, _pack in entries]
    if select in keys:
        wm.scatter_active_biome_index = keys.index(select)
    wm.scatter_active_biome_index = min(wm.scatter_active_biome_index, max(len(keys) - 1, 0))


def _biome_pick_items(self, context):
    """Enum items for the biome picker: one preview per listed biome."""
    _biome_pick_cache.clear()
    fallback = icon_utils.get_builtin_icon_value('ASSET_MANAGER')
    prefs = get_addon_prefs(context)
    for index, item in enumerate(context.window_manager.scatter_biomes):
        if not item.valid or (prefs is not None and not is_biome_in_group(item, prefs.biome_group)):
            continue
        description = item.description or f"Load \"{item.label}\" into the active ground"
        icon = icon_utils.get_biome_icon_id(item.name) or fallback
        _biome_pick_cache.append((item.name, item.label, description, icon, index))
    return _biome_pick_cache


def _deferred_refresh():
    try:
        refresh_biome_library()
    except (AttributeError, RuntimeError):
        pass
    return None


@persistent
def _refresh_after_load(_dummy):
    """Rescan the biome library after a file load, which replaces the window-manager lists."""
    if not bpy.app.timers.is_registered(_deferred_refresh):
        bpy.app.timers.register(_deferred_refresh, first_interval=0.1)


def _biome_info_lines(item):
    """Return the summary lines shown for a listed biome."""
    systems = item.manual_count + item.procedural_count
    lines = [f"Pack: {item.pack_name}"] if item.pack_id else []
    lines += [
        f"{systems} system(s): {item.procedural_count} procedural, {item.manual_count} paint",
        f"Created: {item.created.replace('T', ' ')}",
    ]
    if item.modified and item.modified != item.created:
        lines.append(f"Modified: {item.modified.replace('T', ' ')}")
    return lines


def get_listed_biome(context, name):
    for item in context.window_manager.scatter_biomes:
        if item.name == name:
            return item
    return None


def _refuse_pack_biome(operator, biome_name):
    """Report and return True when the biome belongs to an installed pack."""
    if not biomes_utils.split_biome_key(biome_name)[0]:
        return False
    operator.report({'WARNING'}, "Biomes from a pack are read-only — uninstall the pack instead")
    return True


#----ASSET REFERENCES----
def _describe_asset(idb):
    """Return a library source key, or member list for local collections, plus the name."""
    entry = {"name": idb.name}
    source = library_ops.get_asset_source(idb)
    if source:
        entry["source"] = source
    elif isinstance(idb, bpy.types.Collection):
        entry["members"] = [_describe_asset(member) for member in (*idb.objects, *idb.children)]
    return entry


def _resolve_asset(entry, scene, pack_root):
    """Reuse or append an asset from its source, rebuild local collections, else find by name."""
    if not isinstance(entry, dict):
        return None
    name = entry.get("name") if isinstance(entry.get("name"), str) else ""
    if pack_root is None:
        source = entry.get("source")
    else:
        source = biomes_utils.resolve_pack_source(pack_root, entry.get("pack_source"))
    if isinstance(source, str):
        found = library_ops.resolve_library_asset(source)
        if found is not None:
            return found
    members = entry.get("members")
    if isinstance(members, list) and name:
        collection = biomes_utils.find_scene_collection(scene, name)
        if collection is None:
            collection = library_ops.ensure_scatter_subcollection(name)
        for member in members:
            idb = _resolve_asset(member, scene, pack_root)
            if idb is not None:
                library_ops.link_under(collection, idb)
        return collection
    return (
        biomes_utils.find_scene_object(scene, name)
        or biomes_utils.find_scene_collection(scene, name)
    )


def _resolve_instance(entry, scene, pack_root, wanted_type, unresolved):
    """Resolve an instances picker reference of the wanted type, counting failures."""
    if not isinstance(entry, dict):
        return None
    idb = _resolve_asset(entry, scene, pack_root)
    if isinstance(idb, bpy.types.Object) and not is_pickable_mesh(idb):
        idb = None
    if not isinstance(idb, wanted_type):
        unresolved.append(str(entry.get("name", "?")))
        return None
    return idb


#----BIOME APPLY----
def _apply_instances(system, block, scene, pack_root, unresolved):
    obj = _resolve_instance(block.get("object"), scene, pack_root, bpy.types.Object, unresolved)
    collection = _resolve_instance(
        block.get("collection"), scene, pack_root, bpy.types.Collection, unresolved,
    )
    mode = 1 if block.get("mode") == 1 else 0
    if system.system_type == 'MANUAL':
        modifier = geonodes_utils.add_manual_instances_modifier(system.curve_obj)
        system.manual_instances_mode = mode
        if obj is not None:
            system.manual_instances_object = obj
        if collection is not None:
            system.manual_instances_collection = collection
        geonodes_utils.apply_manual_instances_assignment(system)
    else:
        modifier = geonodes_utils.add_instances_modifier(system.curve_obj)
        system.instances_mode = mode
        if obj is not None:
            system.instances_object = obj
        if collection is not None:
            system.instances_collection = collection
        geonodes_utils.apply_instances_assignment(system)
    biomes_utils.apply_sockets(modifier, block.get("sockets", {}))


def _apply_system(context, ground, entry, pack_root, skipped, unresolved):
    """Create one stored system on the ground with its distribution, instances and effectors."""
    scene = context.scene
    name = entry.get("name") if isinstance(entry.get("name"), str) else None
    system, _warning = create_system(context, ground, entry["system_type"], name)
    if system.curve_obj is None:
        return
    biomes_utils.apply_sockets(
        geonodes_utils.get_procedural_modifier(system), entry.get("points", {}),
    )
    if entry.get("instances"):
        _apply_instances(system, entry["instances"], scene, pack_root, unresolved)
    for effector_entry in reversed(entry.get("effectors", [])):
        effector_type = effector_entry["type"]
        label = EFFECTOR_TYPE_LABELS.get(effector_type, effector_type)
        if effector_type not in geonodes_utils.EFFECTOR_NODE_GROUPS:
            skipped.append(label)
            continue
        if system.system_type == 'MANUAL' and effector_type in PROCEDURAL_ONLY_EFFECTORS:
            skipped.append(label)
            continue
        effector = create_effector(system, effector_type)
        if effector is None:
            skipped.append(label)
            continue
        unresolved += biomes_utils.apply_effector_entry(
            system, effector, effector_entry, scene, pack_root,
        )
    system.active_effector_index = 0
    system.curve_obj.hide_viewport = bool(entry.get("hide_viewport", False))
    system.curve_obj.hide_render = bool(entry.get("hide_render", False))


def _load_biome(operator, context, biome_key):
    """Add every system of a saved or pack biome to the active ground and report one summary."""
    ground = _get_active_ground(context)
    if ground is None or ground.target_object is None:
        operator.report({'ERROR'}, "Active ground has no target object")
        return {'CANCELLED'}
    if not biome_key:
        operator.report({'WARNING'}, "No biome selected")
        return {'CANCELLED'}
    biome_name = biomes_utils.split_biome_key(biome_key)[1]
    try:
        data = biomes_utils.read_biome(biome_key)
    except ValueError as error:
        operator.report({'ERROR'}, f"Could not load biome \"{biome_name}\": {error}")
        return {'CANCELLED'}
    pack_root = biomes_utils.get_pack_root(biome_key)
    skipped = []
    unresolved = []
    for entry in reversed(data["systems"]):
        _apply_system(context, ground, entry, pack_root, skipped, unresolved)
    ground.active_scatter_system_index = 0
    context.view_layer.update()
    message = f"Loaded biome \"{biome_name}\": {len(data['systems'])} system(s)"
    if skipped:
        message += f"; skipped masks: {', '.join(skipped)}"
    if unresolved:
        message += f"; left empty: {', '.join(sorted(set(unresolved)))}"
    operator.report({'WARNING'} if skipped or unresolved else {'INFO'}, message)
    return {'FINISHED'}


#----BIOME LIBRARY STATE----
class SCATTER_BiomeItem(PropertyGroup):
    """One saved or pack biome file as listed by the biome library."""
    name: StringProperty(name="Key")
    label: StringProperty(name="Name")
    pack_id: StringProperty(name="Pack folder")
    pack_name: StringProperty(name="Pack")
    pack_include: BoolProperty(name="Include", description="Include this biome in the pack export")
    description: StringProperty(name="Description")
    created: StringProperty(name="Created")
    modified: StringProperty(name="Modified")
    manual_count: IntProperty(name="Paint systems")
    procedural_count: IntProperty(name="Procedural systems")
    file_path: StringProperty(name="File", subtype='FILE_PATH')
    valid: BoolProperty(name="Valid", default=True)


class SCATTER_PackItem(PropertyGroup):
    """One installed biome pack as listed by the biome library."""
    name: StringProperty(name="Folder")
    title: StringProperty(name="Name")
    version: StringProperty(name="Version")
    author: StringProperty(name="Author")
    biome_count: IntProperty(name="Biomes")
    asset_library: StringProperty(name="Asset Library")
    valid: BoolProperty(name="Valid", default=True)


#----BIOME BROWSER----
class SCATTER_OT_open_biome_browser(Operator):
    bl_idname = "scatter.open_biome_browser"
    bl_label = "Scatter Biomes"
    bl_description = "Pick a saved biome by its preview and load it into the active ground"
    bl_options = {'UNDO'}

    @classmethod
    def poll(cls, context):
        return _get_active_ground(context) is not None

    def invoke(self, context, event):
        refresh_biome_library(context)
        sync_biome_selection(context)
        # a dialog stays open while a preview is picked and closes on Load
        return context.window_manager.invoke_props_dialog(
            self, width=_BROWSER_WIDTH, title="Scatter Biomes", confirm_text="Load Biome",
        )

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        prefs = get_addon_prefs(context)
        layout.operator("scatter.save_biome", text="Save Biome Preset", icon='FILE_TICK')
        group = BIOME_GROUP_LOCAL
        if prefs is not None:
            layout.prop(prefs, "biome_group", text="")
            group = prefs.biome_group
        if not any(item.valid and is_biome_in_group(item, group) for item in wm.scatter_biomes):
            row = layout.row()
            row.enabled = False
            imported = group == BIOME_GROUP_IMPORTED
            row.label(text="No packs installed yet" if imported else "No biomes saved yet")
            return
        layout.template_icon_view(
            wm, "scatter_biome_pick", show_labels=True,
            scale=_THUMBNAIL_SCALE, scale_popup=_THUMBNAIL_SCALE,
        )
        item = get_listed_biome(context, wm.scatter_biome_pick)
        if item is None:
            return
        info = layout.column(align=True)
        info.active = False
        if item.description:
            info.label(text=item.description)
        for line in _biome_info_lines(item):
            info.label(text=line)

    def execute(self, context):
        return _load_biome(self, context, context.window_manager.scatter_biome_pick)


class SCATTER_OT_save_biome(Operator):
    bl_idname = "scatter.save_biome"
    bl_label = "Save Biome"
    bl_description = "Save every scatter system of the active ground as a biome"
    bl_options = {'REGISTER'}

    name: StringProperty(name="Name", default="")
    capture_preview: BoolProperty(
        name="Capture viewport as preview",
        description="Render the 3D viewport (without overlays) as the biome's square thumbnail",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        ground = _get_active_ground(context)
        return ground is not None and len(ground.scatter_systems) > 0

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "name")
        layout.prop(self, "capture_preview")
        if biomes_utils.biome_exists(self.name):
            layout.label(text="Biome exists, it will be overwritten")

    def execute(self, context):
        safe_name = biomes_utils.sanitize_biome_name(self.name)
        if not safe_name:
            self.report({'ERROR'}, "Enter a biome name")
            return {'CANCELLED'}
        try:
            previous = biomes_utils.read_biome(safe_name)
        except ValueError:
            previous = None
        data = biomes_utils.serialize_ground(_get_active_ground(context), safe_name, _describe_asset)
        description = str(previous.get("description", "")) if previous else ""
        biomes_utils.stamp_biome(data, description, previous)
        try:
            biomes_utils.write_biome(safe_name, data)
        except OSError as error:
            self.report({'ERROR'}, f"Could not save biome: {error}")
            return {'CANCELLED'}
        message = f"Saved biome \"{safe_name}\" ({len(data['systems'])} system(s))"
        level = 'INFO'
        if self.capture_preview:
            try:
                biomes_utils.capture_thumbnail(context, safe_name)
            except (OSError, RuntimeError) as error:
                message += f"; no preview captured: {error}"
                level = 'WARNING'
        refresh_biome_library(context, select=safe_name)
        self.report({level}, message)
        return {'FINISHED'}


class SCATTER_OT_capture_biome_preview(Operator):
    bl_idname = "scatter.capture_biome_preview"
    bl_label = "Capture Preview"
    bl_description = "Render the 3D viewport (without overlays) as the biome's square thumbnail"
    bl_options = {'REGISTER'}

    biome_name: StringProperty(options={'HIDDEN'})

    def execute(self, context):
        if _refuse_pack_biome(self, self.biome_name):
            return {'CANCELLED'}
        try:
            biomes_utils.capture_thumbnail(context, self.biome_name)
        except (OSError, RuntimeError) as error:
            self.report({'ERROR'}, f"Could not capture the preview: {error}")
            return {'CANCELLED'}
        refresh_biome_library(context, select=self.biome_name)
        return {'FINISHED'}


class SCATTER_OT_load_biome(Operator):
    bl_idname = "scatter.load_biome"
    bl_label = "Load Biome"
    bl_description = "Add the scatter systems of the selected biome to the active ground"
    bl_options = {'REGISTER', 'UNDO'}

    biome_name: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return _get_active_ground(context) is not None

    @classmethod
    def description(cls, context, properties):
        item = get_listed_biome(context, properties.biome_name)
        if item is None:
            return cls.bl_description
        lines = [item.description] if item.description else []
        lines += _biome_info_lines(item)
        lines.append("Click to add these systems to the active ground")
        return "\n".join(lines)

    def execute(self, context):
        return _load_biome(self, context, self.biome_name)


class SCATTER_OT_select_biome(Operator):
    bl_idname = "scatter.select_biome"
    bl_label = "Select Biome"
    bl_description = "Select this biome in the library"
    bl_options = {'INTERNAL'}

    index: IntProperty(options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        biomes = context.window_manager.scatter_biomes
        if not 0 <= properties.index < len(biomes):
            return cls.bl_description
        item = biomes[properties.index]
        return f"{item.label} — {item.pack_name}" if item.pack_id else item.label

    def execute(self, context):
        wm = context.window_manager
        if not 0 <= self.index < len(wm.scatter_biomes):
            return {'CANCELLED'}
        wm.scatter_active_biome_index = self.index
        return {'FINISHED'}


class SCATTER_OT_refresh_biomes(Operator):
    bl_idname = "scatter.refresh_biomes"
    bl_label = "Refresh Biomes"
    bl_description = "Rescan the biome folder"
    bl_options = {'REGISTER'}

    def execute(self, context):
        refresh_biome_library(context)
        return {'FINISHED'}


class SCATTER_OT_rename_biome(Operator):
    bl_idname = "scatter.rename_biome"
    bl_label = "Rename Biome"
    bl_description = "Rename the biome file and its thumbnail"
    bl_options = {'REGISTER'}

    biome_name: StringProperty(options={'HIDDEN'})
    new_name: StringProperty(name="New Name")

    def invoke(self, context, event):
        if _refuse_pack_biome(self, self.biome_name):
            return {'CANCELLED'}
        self.new_name = self.biome_name
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, "new_name")

    def execute(self, context):
        if _refuse_pack_biome(self, self.biome_name):
            return {'CANCELLED'}
        try:
            renamed = biomes_utils.rename_biome(self.biome_name, self.new_name)
        except (OSError, ValueError) as error:
            self.report({'ERROR'}, f"Could not rename biome: {error}")
            return {'CANCELLED'}
        refresh_biome_library(context, select=renamed)
        return {'FINISHED'}


class SCATTER_OT_set_biome_preview(Operator):
    bl_idname = "scatter.set_biome_preview"
    bl_label = "Set Preview"
    bl_description = "Pick an image as the preview thumbnail of the biome"
    bl_options = {'REGISTER'}

    biome_name: StringProperty(options={'HIDDEN'})
    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default=_PREVIEW_FILTER, options={'HIDDEN'})

    def invoke(self, context, event):
        if _refuse_pack_biome(self, self.biome_name):
            return {'CANCELLED'}
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if _refuse_pack_biome(self, self.biome_name):
            return {'CANCELLED'}
        try:
            biomes_utils.save_thumbnail(self.biome_name, bpy.path.abspath(self.filepath))
        except (OSError, ValueError) as error:
            self.report({'ERROR'}, f"Could not set the preview: {error}")
            return {'CANCELLED'}
        refresh_biome_library(context, select=self.biome_name)
        return {'FINISHED'}


class SCATTER_OT_delete_biome(Operator):
    bl_idname = "scatter.delete_biome"
    bl_label = "Delete Biome"
    bl_description = "Delete the biome file and its thumbnail from disk"
    bl_options = {'REGISTER'}

    biome_name: StringProperty(options={'HIDDEN'})

    def invoke(self, context, event):
        if _refuse_pack_biome(self, self.biome_name):
            return {'CANCELLED'}
        return context.window_manager.invoke_confirm(
            self, event, title="Delete Biome", message=f"Delete \"{self.biome_name}\" from disk?",
            confirm_text="Delete",
        )

    def execute(self, context):
        if _refuse_pack_biome(self, self.biome_name):
            return {'CANCELLED'}
        try:
            biomes_utils.delete_biome(self.biome_name)
        except OSError as error:
            self.report({'ERROR'}, f"Could not delete biome: {error}")
            return {'CANCELLED'}
        refresh_biome_library(context)
        self.report({'INFO'}, f"Deleted biome \"{self.biome_name}\"")
        return {'FINISHED'}


class SCATTER_OT_open_biome_folder(Operator):
    bl_idname = "scatter.open_biome_folder"
    bl_label = "Open Biome Folder"
    bl_description = "Open the biome folder in the file manager"
    bl_options = {'REGISTER'}

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=biomes_utils.get_biome_dir())
        return {'FINISHED'}


class SCATTER_OT_open_biome_preferences(Operator):
    bl_idname = "scatter.open_biome_preferences"
    bl_label = "Biome Settings"
    bl_description = "Open the RAF Scatter preferences to manage biomes"
    bl_options = {'REGISTER'}

    def execute(self, context):
        bpy.ops.preferences.addon_show(module=_ADDON_ID)
        return {'FINISHED'}


classes = (
    SCATTER_BiomeItem,
    SCATTER_PackItem,
    SCATTER_OT_open_biome_browser,
    SCATTER_OT_save_biome,
    SCATTER_OT_capture_biome_preview,
    SCATTER_OT_load_biome,
    SCATTER_OT_select_biome,
    SCATTER_OT_refresh_biomes,
    SCATTER_OT_rename_biome,
    SCATTER_OT_set_biome_preview,
    SCATTER_OT_delete_biome,
    SCATTER_OT_open_biome_folder,
    SCATTER_OT_open_biome_preferences,
)


def register():
    bpy.types.WindowManager.scatter_biomes = CollectionProperty(type=SCATTER_BiomeItem)
    bpy.types.WindowManager.scatter_packs = CollectionProperty(type=SCATTER_PackItem)
    bpy.types.WindowManager.scatter_active_biome_index = IntProperty(default=0)
    bpy.types.WindowManager.scatter_biome_pick = EnumProperty(
        name="Biome", description="Select the biome to load", items=_biome_pick_items,
    )
    bpy.app.timers.register(_deferred_refresh, first_interval=0.5)
    bpy.app.handlers.load_post.append(_refresh_after_load)


def unregister():
    if _refresh_after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_refresh_after_load)
    if bpy.app.timers.is_registered(_deferred_refresh):
        bpy.app.timers.unregister(_deferred_refresh)
    del bpy.types.WindowManager.scatter_biome_pick
    del bpy.types.WindowManager.scatter_active_biome_index
    del bpy.types.WindowManager.scatter_packs
    del bpy.types.WindowManager.scatter_biomes
