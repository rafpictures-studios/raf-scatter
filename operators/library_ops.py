"""Asset browser integration and asset import into scatter systems."""
import os
import re

import bpy
from bpy.props import StringProperty
from bpy.types import Operator, Panel

from ..utils import geonodes as geonodes_utils

_SHOW_HEADER = False
_SHOW_TOOLBAR = True
_SHOW_ASSET_DETAILS = True
_TAG = "raf_source"
_DEP_TYPES = ("node_groups", "images", "materials", "meshes", "objects", "collections")
_SUFFIX_RE = re.compile(r"\.\d{3,}$")

#----SCATTER COLLECTION----

def _get_or_create_scatter_collection():
    """Return the SCATTER collection, creating it if missing."""
    coll = bpy.data.collections.get("SCATTER")
    if coll is None:
        coll = bpy.data.collections.new("SCATTER")
        coll.color_tag = 'COLOR_04'
        bpy.context.scene.collection.children.link(coll)
        layer_coll = bpy.context.view_layer.layer_collection.children.get("SCATTER")
        if layer_coll is not None:
            layer_coll.exclude = True
    return coll

def _ensure_under(parent, obj=None, coll=None):
    """Link an object or collection under parent unless already inside."""
    if obj is not None and obj.name not in parent.objects:
        parent.objects.link(obj)
    if coll is not None and coll.name not in parent.children:
        parent.children.link(coll)

#----ACTIVE SYSTEM----

def _get_active_system():
    """Return the active scatter system or None."""
    scene = bpy.context.scene
    ground_idx = scene.active_ground_index
    if not (0 <= ground_idx < len(scene.scatter_grounds)):
        return None
    ground = scene.scatter_grounds[ground_idx]
    system_idx = ground.active_scatter_system_index
    if not (0 <= system_idx < len(ground.scatter_systems)):
        return None
    return ground.scatter_systems[system_idx]

def _apply_as_instance(obj, coll, as_collection):
    """Assign the object or collection to the active system."""
    system = _get_active_system()
    if system is None:
        return
    mode = 1 if as_collection else 0
    if system.system_type == 'MANUAL':
        system.manual_instances_mode = mode
        modifier = geonodes_utils.get_manual_instances_modifier(system)
        if modifier is not None:
            geonodes_utils.set_modifier_input_value(modifier, "Instances", mode)
        if obj is not None:
            system.manual_instances_object = obj
        if coll is not None:
            system.manual_instances_collection = coll
    else:
        system.instances_mode = mode
        modifier = geonodes_utils.get_instances_modifier(system)
        if modifier is not None:
            geonodes_utils.set_modifier_input_value(modifier, "Instances", mode)
        if obj is not None:
            system.instances_object = obj
        if coll is not None:
            system.instances_collection = coll

#----ASSET IDENTITY----

def _norm_path(path):
    """Return a normalized absolute path."""
    return os.path.normcase(os.path.normpath(bpy.path.abspath(path)))

def _source_key(filepath, name):
    """Return a stable identity from the normalized library path and asset name."""
    return f"{_norm_path(filepath)}::{name}"

def _tag(idb, key):
    """Stamp an appended datablock with its source key."""
    if idb.library is None:
        idb[_TAG] = key

def _id_key(idb):
    """Return the source key of a datablock."""
    if idb.library is not None:
        return _source_key(idb.library.filepath, idb.name)
    return idb.get(_TAG)

def _find_existing(datablocks, key):
    """Find a datablock matching the source key."""
    for idb in datablocks:
        if _id_key(idb) == key:
            return idb
    return None

def _clear_asset_data(obj_or_coll, context=None):
    """Remove asset metadata so the import is not marked as an asset."""
    if obj_or_coll is None or obj_or_coll.asset_data is None:
        return
    if context is None:
        context = bpy.context
    try:
        with context.temp_override(id=obj_or_coll):
            bpy.ops.asset.clear(set_fake_user=False)
    except (TypeError, RuntimeError):
        try:
            if hasattr(obj_or_coll, 'select_set'):
                bpy.ops.object.select_all(action='DESELECT')
                obj_or_coll.select_set(True)
                context.view_layer.objects.active = obj_or_coll
                bpy.ops.asset.clear(set_fake_user=False)
        except (RuntimeError, AttributeError):
            pass

#----ASSET LOADING----

def _snapshot():
    """Record the datablocks that exist before a load."""
    snap = {}
    for dep_type in _DEP_TYPES:
        datablocks = getattr(bpy.data, dep_type)
        tagged = {idb.get(_TAG): idb for idb in datablocks if idb.library is None and idb.get(_TAG)}
        snap[dep_type] = {
            "ptrs": {idb.as_pointer() for idb in datablocks},
            "names": {idb.name for idb in datablocks},
            "tagged": tagged,
        }
    return snap

def _original_name(name, pre_names):
    """Undo Blender's .001 rename caused by a clash with existing data."""
    match = _SUFFIX_RE.search(name)
    if match:
        base = name[:match.start()]
        if base in pre_names:
            return base
    return name

def _find_twin(obj, pre_names):
    """Find the earlier local object that obj was renamed away from."""
    base = _original_name(obj.name, pre_names)
    twin = bpy.data.objects.get(base) if base != obj.name else None
    if twin is None or twin.type != obj.type or twin.get(_TAG) not in (None, obj.get(_TAG)):
        return None
    if obj.type == 'MESH':
        if len(twin.data.vertices) != len(obj.data.vertices):
            return None
        if len(twin.data.polygons) != len(obj.data.polygons):
            return None
    return twin

def _link_object_data(source, target):
    """Share the object data of source with target."""
    if source.data is None or source.data == target.data:
        return
    old_data = target.data
    old_materials = [slot.material for slot in target.material_slots if slot.material]
    target.data = source.data
    orphans = [idb for idb in (old_data, *old_materials) if idb.users == 0]
    if orphans:
        bpy.data.batch_remove(orphans)

def _dedupe_new_data(filepath, snap, keep):
    """Merge freshly appended data into earlier imports."""
    merged = 0
    for dep_type in _DEP_TYPES:
        datablocks = getattr(bpy.data, dep_type)
        pre = snap[dep_type]
        new_ids = [
            idb for idb in datablocks
            if idb.as_pointer() not in pre["ptrs"]
            and idb.as_pointer() not in keep
            and idb.library is None
        ]
        for idb in new_ids:
            key = _source_key(filepath, _original_name(idb.name, pre["names"]))
            old = pre["tagged"].get(key)
            if old is not None and old != idb:
                idb.user_remap(old)
                datablocks.remove(idb)
                merged += 1
                continue
            _tag(idb, key)
            _clear_asset_data(idb)
    return merged

def _recover_loaded(datablocks, before, name, filepath, link):
    """Find a datablock that was loaded but is missing from the load result."""
    for idb in datablocks:
        if idb.as_pointer() in before["ptrs"]:
            continue
        if link:
            if idb.library is None or _norm_path(idb.library.filepath) != _norm_path(filepath):
                continue
            if idb.name == name:
                return idb
        elif idb.library is None and _original_name(idb.name, before["names"]) == name:
            return idb
    return None

def _load_assets(filepath, names, link):
    """Load all names in one call so shared dependencies stay shared."""
    before = {
        dep_type: {
            "ptrs": {idb.as_pointer() for idb in getattr(bpy.data, dep_type)},
            "names": {idb.name for idb in getattr(bpy.data, dep_type)},
        }
        for dep_type in ("objects", "collections")
    }
    with bpy.data.libraries.load(filepath, link=link) as (data_from, data_to):
        file_objects = list(data_from.objects)
        file_collections = list(data_from.collections)
        obj_names = [n for n in names if n in data_from.objects]
        coll_names = [n for n in names if n not in obj_names and n in data_from.collections]
        # copies: Blender replaces the assigned list items with the loaded IDs
        data_to.objects = list(obj_names)
        data_to.collections = list(coll_names)

    objs = {n: o for n, o in zip(obj_names, data_to.objects) if o is not None}
    colls = {n: c for n, c in zip(coll_names, data_to.collections) if c is not None}

    for name in obj_names:
        if name not in objs:
            found = _recover_loaded(bpy.data.objects, before["objects"], name, filepath, link)
            if found is not None:
                objs[name] = found
                print(f"[RAF] Recovered '{name}' from the datablocks added by the load")

    for name in coll_names:
        if name not in colls:
            found = _recover_loaded(bpy.data.collections, before["collections"], name, filepath, link)
            if found is not None:
                colls[name] = found
                print(f"[RAF] Recovered '{name}' from the datablocks added by the load")

    missing = [n for n in names if n not in objs and n not in colls]
    if missing:
        print(f"[RAF] Not loaded from '{filepath}': {missing[:5]} | "
              f"file objects: {file_objects[:30]} | file collections: {file_collections[:10]}")
    return objs, colls, missing

def _resolve_assets(filepath, names, link):
    """Return (objects, collections, reused_names, failed_names) keyed by asset name."""
    objs, colls, reused, to_load = {}, {}, set(), []
    for name in names:
        key = _source_key(filepath, name)
        obj = _find_existing(bpy.data.objects, key)
        if obj is not None:
            objs[name] = obj
            reused.add(name)
            continue
        coll = _find_existing(bpy.data.collections, key)
        if coll is not None:
            colls[name] = coll
            reused.add(name)
            continue
        to_load.append(name)

    failed = []
    if to_load:
        snap = None if link else _snapshot()
        try:
            new_objs, new_colls, failed = _load_assets(filepath, to_load, link)
        except (OSError, RuntimeError) as exc:
            print(f"[RAF] Library load failed: {exc}")
            return objs, colls, reused, list(to_load)

        for name, obj in new_objs.items():
            _tag(obj, _source_key(filepath, name))
            _clear_asset_data(obj)
            objs[name] = obj

        for name, coll in new_colls.items():
            _tag(coll, _source_key(filepath, name))
            _clear_asset_data(coll)
            colls[name] = coll

        if snap is not None:
            for obj in new_objs.values():
                twin = _find_twin(obj, snap["objects"]["names"])
                if twin is not None:
                    _link_object_data(twin, obj)
                    print(f"[RAF] Linked object data of '{obj.name}' to '{twin.name}'")
            keep = {idb.as_pointer() for idb in (*new_objs.values(), *new_colls.values())}
            merged = _dedupe_new_data(filepath, snap, keep)
            if merged:
                print(f"[RAF] Merged {merged} duplicate datablock(s) into earlier imports")

    return objs, colls, reused, failed

#----PUBLIC ACCESS----

def get_asset_source(idb):
    """Return the library source key of an imported object or collection, or None."""
    return _id_key(idb)

def resolve_library_asset(source):
    """Reuse or append the asset behind a source key and keep it under SCATTER."""
    filepath, _sep, name = source.rpartition("::")
    if not filepath or not name or not os.path.isfile(filepath):
        return None
    objs, colls, _reused, _failed = _resolve_assets(filepath, [name], link=False)
    scatter_coll = _get_or_create_scatter_collection()
    if name in objs:
        _ensure_under(scatter_coll, obj=objs[name])
        return objs[name]
    if name in colls:
        _ensure_under(scatter_coll, coll=colls[name])
        return colls[name]
    return None

def ensure_scatter_subcollection(name):
    """Return a collection with this name under SCATTER, creating it when missing."""
    scatter_coll = _get_or_create_scatter_collection()
    existing = bpy.data.collections.get(name)
    if existing is not None and existing.name in [c.name for c in scatter_coll.children_recursive]:
        return existing
    collection = bpy.data.collections.new(name)
    scatter_coll.children.link(collection)
    return collection

def link_under(parent, idb):
    """Link an object or collection under parent unless already inside."""
    if isinstance(idb, bpy.types.Collection):
        _ensure_under(parent, coll=idb)
    else:
        _ensure_under(parent, obj=idb)

#----SELECTED ASSETS----

def _asset_entries(context):
    """Return (filepath, name, id_type) for every selected asset stored in a library file."""
    entries = []
    for asset in getattr(context, "selected_assets", None) or ():
        if asset.local_id is None and asset.full_library_path:
            entries.append((asset.full_library_path, asset.name, asset.id_type))
    return entries

def _asset_paths(context):
    """Map each selected asset name to the library file it is stored in."""
    return {name: filepath for filepath, name, _id_type in _asset_entries(context)}

def _print_source_dump(context, paths):
    """Print what the Asset Browser exposes for the current selection."""
    asset = context.asset
    active = (asset.name, asset.id_type, asset.full_library_path) if asset else None
    files = [(f.name, f.relative_path) for f in context.selected_files]
    print(f"[RAF Scatter] Import source: files={files} assets={_asset_entries(context)} active={active} paths={paths}")

#----ASSET BROWSER----

def _close_asset_browser_windows():
    """Timer callback that closes every temporary Asset Browser window."""
    windows = list(bpy.context.window_manager.windows)
    for window in windows[1:]:
        areas = window.screen.areas
        if len(areas) == 1 and areas[0].ui_type == 'ASSETS':
            try:
                with bpy.context.temp_override(window=window, screen=window.screen):
                    bpy.ops.wm.window_close()
            except (TypeError, RuntimeError):
                pass
    return None

def _close_asset_browser():
    """Close the Asset Browser windows once the running operator has returned."""
    bpy.app.timers.register(_close_asset_browser_windows, first_interval=0.1)

def _get_default_library_name():
    """Return the default library name from the addon preferences, '' for all."""
    addon = bpy.context.preferences.addons.get(__package__.split(".")[0])
    prefs = addon.preferences if addon else None
    name = getattr(prefs, "default_library", "")
    return "" if name in ("", "ALL") else name

def _apply_default_library(params):
    """Apply the default library reference to the asset browser params."""
    lib_name = _get_default_library_name()
    if not lib_name:
        return
    prop = params.bl_rna.properties.get('asset_library_reference')
    items = list(prop.enum_items) if prop is not None else []
    candidates = [i.identifier for i in items if i.name == lib_name or i.identifier == lib_name]
    candidates.append(lib_name)
    for ident in dict.fromkeys(candidates):
        try:
            params.asset_library_reference = ident
            print(f"[RAF] Default library applied: '{lib_name}' ({ident})")
            return
        except (TypeError, ValueError):
            continue
    available = [(i.identifier, i.name) for i in items]
    print(f"[RAF] Default library '{lib_name}' not applied; available: {available}")

#----OPERATORS----

class SCATTER_OT_open_library(Operator):
    """Open the Asset Browser"""
    bl_idname = "scatter.open_library"
    bl_label = "Open Library"
    bl_options = {'REGISTER'}

    def execute(self, context):
        old_windows = set(context.window_manager.windows)
        bpy.ops.wm.window_new()
        new_window = next((w for w in context.window_manager.windows if w not in old_windows), None)
        if new_window is None:
            self.report({'WARNING'}, "Failed to create window")
            return {'CANCELLED'}

        area = new_window.screen.areas[0]
        area.ui_type = 'ASSETS'
        tries = 0

        def _setup():
            nonlocal tries
            tries += 1
            area = new_window.screen.areas[0]
            space = area.spaces.active
            params = getattr(space, 'params', None)
            if params is None:
                return 0.1 if tries < 30 else None
            try:
                params.use_filter_blendid = True
                fa = params.filter_asset_id
                for name in dir(fa):
                    if name.startswith("filter_"):
                        setattr(fa, name, name in ("filter_object", "filter_collection"))
            except (AttributeError, TypeError):
                pass
            _apply_default_library(params)
            space.show_region_header = _SHOW_HEADER
            space.show_region_toolbar = _SHOW_TOOLBAR
            space.show_region_tool_props = _SHOW_ASSET_DETAILS
            print("[RAF] Asset Browser configured")
            return None

        bpy.app.timers.register(_setup, first_interval=0.1)
        return {'FINISHED'}

class SCATTER_OT_open_preferences(Operator):
    """Open Blender Preferences at File Paths"""
    bl_idname = "scatter.open_preferences"
    bl_label = "Open Preferences"
    bl_options = {'REGISTER'}

    def execute(self, context):
        bpy.ops.screen.userpref_show()
        try:
            bpy.context.preferences.active_section = 'FILE_PATHS'
            print("[RAF Scatter] Preferences set to FILE_PATHS")
        except (AttributeError, TypeError):
            pass
        return {'FINISHED'}

class SCATTER_OT_import_selected(Operator):
    """Import the selected asset(s) into the scene"""
    bl_idname = "scatter.import_selected"
    bl_label = "Import Selected Asset"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: StringProperty(
        name="Collection Name",
        description="Name for the collection (auto-recommended from asset names)",
    )

    def invoke(self, context, event):
        selected = context.selected_files
        if selected and len(selected) > 1:
            names = [f.name for f in selected if f.name]
            self.collection_name = self._recommend_name(names)
            return context.window_manager.invoke_props_dialog(self, width=300)
        return self.execute(context)

    def draw(self, context):
        layout = self.layout
        count = len(context.selected_files)
        layout.label(text=f"Import {count} asset{'s' if count > 1 else ''}:")
        if count > 1:
            layout.prop(self, "collection_name")

    def execute(self, context):
        selected = context.selected_files
        if not selected:
            self.report({'WARNING'}, "No assets selected")
            return {'CANCELLED'}

        params = context.space_data.params
        link = (params.import_method == 'LINK')

        if len(selected) == 1:
            result = self._import_single(context, selected[0], link)
        else:
            result = self._import_multiple(context, selected, link)

        if result == {'FINISHED'}:
            _close_asset_browser()

        return result

    def _get_source(self, context):
        """Return (filepath, name) from the active asset or file."""
        asset = context.asset
        if asset and asset.local_id is None:
            return asset.full_library_path, asset.name
        active = context.active_file
        if active:
            path = getattr(active, 'full_library_path', None)
            name = getattr(active, 'name', None)
            if path:
                return path, name
        return None, None

    def _import_single(self, context, file, link):
        filepath, name = self._get_source(context)
        if filepath is None or not filepath:
            self.report({'WARNING'}, "Cannot determine source file")
            return {'CANCELLED'}

        with bpy.data.libraries.load(filepath, link=link) as (data_from, data_to):
            if name in data_from.objects:
                data_to.objects = [name]
            elif name in data_from.collections:
                data_to.collections = [name]
            else:
                self.report({'WARNING'}, f"'{name}' not found in library")
                return {'CANCELLED'}

        obj = bpy.data.objects.get(name)
        if obj is not None:
            scatter_coll = _get_or_create_scatter_collection()
            scatter_coll.objects.link(obj)
            _clear_asset_data(obj)
            _apply_as_instance(obj=obj, coll=None, as_collection=False)
            self.report({'INFO'}, f"Imported '{name}' as instance object")
            return {'FINISHED'}

        coll = bpy.data.collections.get(name)
        if coll is not None:
            scatter_coll = _get_or_create_scatter_collection()
            scatter_coll.children.link(coll)
            _clear_asset_data(coll)
            _apply_as_instance(obj=None, coll=coll, as_collection=True)
            self.report({'INFO'}, f"Imported collection '{name}' as instance collection")
            return {'FINISHED'}

        self.report({'WARNING'}, "Import failed")
        return {'CANCELLED'}

    def _get_target_collection(self, scatter_coll, collection_name):
        """Reuse a same-named collection under SCATTER, else create one."""
        return ensure_scatter_subcollection(collection_name)

    def _import_multiple(self, context, files, link):
        """Import multiple assets into a single collection."""
        collection_name = self.collection_name
        if not collection_name:
            self.report({'WARNING'}, "Collection name is required")
            return {'CANCELLED'}
        filepath, _ = self._get_source(context)
        if not filepath:
            self.report({'WARNING'}, "Cannot determine source file")
            return {'CANCELLED'}

        names = list(dict.fromkeys(f.name for f in files if f.name))
        objs, colls, reused, failed = _resolve_assets(filepath, names, link)
        if not objs and not colls:
            self.report({'WARNING'}, "Import failed: no assets could be loaded")
            return {'CANCELLED'}

        scatter_coll = _get_or_create_scatter_collection()
        collection = self._get_target_collection(scatter_coll, collection_name)
        for obj in objs.values():
            _ensure_under(collection, obj=obj)
        for coll in colls.values():
            _ensure_under(collection, coll=coll)
        _apply_as_instance(obj=None, coll=collection, as_collection=True)

        total = len(objs) + len(colls)
        msg = f"Imported {total - len(reused)} new asset(s) into '{collection.name}'"
        if reused:
            reused_preview = ", ".join(sorted(reused)[:5])
            msg += f", reused {len(reused)} already imported ({reused_preview})"
        if failed:
            failed_preview = ", ".join(failed[:5])
            msg += f" ({len(failed)} failed: {failed_preview})"
        self.report({'INFO'}, msg)
        return {'FINISHED'}

    @staticmethod
    def _recommend_name(names):
        """Recommend a collection name from a list of asset names."""
        if len(names) < 2:
            return ""
        prefix = os.path.commonprefix(names).rstrip('_-. ')
        return prefix if len(prefix) >= 3 else ""

#----PANELS----

class SCATTER_PT_library(Panel):
    """Scatter import controls for the Asset Browser"""
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "RAF Scatter"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space and space.browse_mode == 'ASSETS'

    def draw(self, context):
        layout = self.layout
        if context.selected_files:
            row = layout.row()
            row.scale_y = 1.3
            row.operator("scatter.import_selected", icon='IMPORT')
        else:
            layout.label(text="No assets selected", icon='INFO')

#----REGISTRATION----

classes = (
    SCATTER_OT_open_library,
    SCATTER_OT_open_preferences,
    SCATTER_OT_import_selected,
    SCATTER_PT_library,
)