# Raf Scatter — AI Agent & Developer Guide

> **⚠️ CRITICAL INSTRUCTIONS FOR AI AGENTS / CODING ASSISTANTS:**
> Read this document entirely before generating, refactoring, or modifying any code for this project. This addon has strict UI/UX preferences, a rigid dependency chain, and a modular architecture that is now the active baseline (see Section 1).
> - **NEVER guess Blender icon names.** Invalid icons will silently throw an exception mid-`draw()` and blank out the rest of the UI panel. Always verify against Blender's official icon enum.
> - **NEVER add a "Convert" or "Change Type" feature** for Scatter Systems (Manual/Procedural). The choice is strictly irreversible once made.
> - **Keep UI drawing decoupled** from data models and operator logic to allow future viewport/gizmo integrations and custom icon swapping without breaking core functionality.
> - **Language Rule:** ALL text in this codebase MUST be in English — this includes user-facing UI text (labels, button texts, tooltips, popup messages) AND code comments/docstrings. No exceptions, no dev-facing Indonesian notes. Keep comments short and only where they add real value; avoid long or frequent comment blocks — a single concise line beats a paragraph.
> - **Conflict Resolution Rule:** if anything in a newly uploaded/pasted code file contradicts this guide, DO NOT silently pick one side. Flag the conflict explicitly to the user and ask which one is correct before proceeding. Once the user decides, update this guide to match — the guide must never be allowed to drift out of sync with the actual codebase.
> - **Edit Mode:** once the modular package exists (it does, see Section 1), prefer targeted edits — per file, per function/class — over regenerating whole files from scratch, unless the user explicitly asks for a full rewrite or a file is trivially short. This keeps diffs reviewable and avoids silently overwriting settled work.
> - **Vibe Coding Checkpoint Rule (see Section 10):** any feature an agent implements is PENDING VERIFICATION until the author explicitly confirms it works in Blender. Do not build further logic on top of an unverified feature without flagging that dependency to the author first.
> - **Import Discipline Check:** whenever an agent edits or reviews a file that calls into another module (e.g. `geonodes_utils.*`, `icon_utils.*`), verify the corresponding `from ..module import x as y` line actually exists at the top of that file before treating the logic as correct. A missing import is a silent `NameError` mid-`draw()`/`execute()` — same failure class as Rule E's icon warning — so check it by default, not only when asked.
> - **Debug Own Code First:** when a UI control doesn't reflect an underlying data/property change (a subtype, default value, range, etc.), audit the exact draw call in this codebase (explicit args like `slider=`, hardcoded `min`/`max`, cached enum lists) BEFORE attributing it to Blender's own behavior, library caching, or any external cause. Self-inflicted bugs are the default suspect, not the environment.
> - **No Unrequested UI Parameters:** don't add display arguments (`slider=`, custom `min`/`max`, icon overrides, etc.) to a control unless the guide or the author asked for it. If a socket's own interface (subtype, range) already defines how it should look, let it render naturally — don't re-decide the presentation in Python on top of it.
---

## 1. Project Overview
A custom Blender addon that allows users to scatter points onto a target surface—either manually using sculpt-style brushes or procedurally—and then modify the distribution through a stack of Geometry Nodes-driven "Effectors".

- **Addon Name (Finalized):** `RAF Scatter` (all-caps RAF). Chosen over "eco"/"ecosystem"-based names because those terms are already heavily used as generic feature descriptors by existing competitors (OpenScatter, Eco-Scatter, Ecosystem Generator), risking brand confusion with existing marketplace products. "Ecosystem" is retained only as a **tagline** — e.g. *"RAF Scatter — Ecosystem scattering toolkit for Blender"* — not as part of the product name itself.
- **Current State:** Dual-track development.
  1. **`raf_scatter/` — the modular addon package.** This is the actual installable addon and the source of truth for anything beyond fast visual iteration: `__init__.py`, `properties.py`, `operators/`, `ui/`, `utils/`, `resources/`. This is the starting point for any agent picking up work — do not propose re-flattening it back into a single file.
  2. **`manual_scatter_addon_prototype*.py` — a single-file UI/UX sketchpad.** Used by the author for fast visual/interaction iteration (paste into Blender Text Editor, Alt+P, no addon install/reload cycle needed). Not the source of truth once a change is confirmed — see Section 8, Sync Workflow.
- **Target State:** A fully modular, professional-grade Blender addon package (`raf_scatter`) with custom icons, dynamic GeoNodes integration, and viewport overlays. The package skeleton for this already exists (see Section 6); remaining work is filling in the GeoNodes/icon TODOs, not restructuring.

---

## 2. Author's Goals & Design Philosophy
- **Modular Architecture:** Done — see Section 6 for the actual layout now in place. Keep new code inside this structure rather than growing any single file too large.
- **Heavy Customization Ready:** Expect future requests for custom icons, UI polish, and viewport-level adjustments (gizmos, overlays). Build with this in mind: keep UI drawing, data models, and operator logic loosely coupled.
- **Design Taste:** Minimalist, compact, and "proper" Blender-native UI. Avoid flashy or non-standard layouts. Use icon-first compact rows over wide text buttons. Use `box()` *only* to group Lists + Toolbars, not for every single section. Use `layout.separator(factor=...)` sparingly for breathing room — favor a few well-placed separators over one after every block.
- **Inline Rename:** Both list UIs (`SCATTER_UL_systems`, `SCATTER_UL_effectors`) support Blender's native double-click-to-rename, by drawing `name` via `row.prop(item, "name", text="", emboss=False)` instead of `row.label()` — same pattern as the Outliner.
- **Minimal List Rows:** `SCATTER_UL_systems` shows only name + type icon. It intentionally does **not** display `target_ground` in the row — `target_ground` is still stored on the PropertyGroup and used internally (Rule A dependency, curve object naming), just not surfaced in the list.
- **Vibe Coding Workflow:** UI and logic are being developed incrementally and in parallel — UI keeps evolving while logic gets layered in feature-by-feature (see Section 10 for how progress is tracked).

---

## 3. Terminology (Do Not Drift From This)
| Term | Meaning & Context |
| :--- | :--- |
| **Target Surface / Target Ground** | The mesh object a scatter system's Curves object attaches to. This is **Step 1** of the whole system. Nothing else can exist without it. One mesh object can only ever be one Target Ground — see Rule F. |
| **Scatter System** | One Curves object + its own modifier stack. Has a fixed `system_type`: `MANUAL` or `PROCEDURAL`, chosen exactly once at creation. |
| **Effector** | One item in a scatter system's modifier stack. Deliberately **NOT** called "Layer". An effector modifies/affects existing points (e.g., density, rotation, collision) rather than generating them from scratch. |

---

## 4. Core Design Rules & Logic

### Rule A: The Dependency Chain (Enforced via `poll()`)
The system operates on a strict, branch-like dependency chain. This is enforced at the Operator level via `poll()` classmethods, not just by hiding UI elements.
1. **Target Surface** (Must exist first)
2. ↳ **Scatter System** (Requires Step 1 to be valid)
3. &nbsp;&nbsp;&nbsp;↳ **Effector** (Requires Step 2 to be valid)

*If a user tries to add a System without a Target Surface, or an Effector without an active System, the operator must be polled out (disabled/hidden).*

### Rule B: Stack Order (Bottom-to-Top) — applies to both Systems and Effectors
- Both the **Scatter System** list and the **Effector** stack behave like Photoshop layers or Blender Modifiers: **Bottom-to-Top**.
- A newly added item (System or Effector) is always inserted at **Index 0** (Top of the list = Top of the stack = Newest).
- The oldest item ends up at the highest index (Bottom of the stack = Base).
- Reordering via `Move Up` / `Move Down` is implemented for **Effectors** (`SCATTER_OT_move_effector` in `operators/effector_ops.py`, wired in `ui/panels.py::draw_effectors`). "Up" moves towards index 0 (top of stack), "Down" moves towards the end.
- Scatter Systems do **not** have Move Up/Down — there is no user-facing need to manually reorder systems relative to each other, only newest-on-top on creation.

### Rule C: Irreversible Scatter System Creation
- Clicking "+" on the Scatter System list opens a small dropdown menu (`SCATTER_MT_add_system_type`): Manual or Procedural. Clicking a choice executes `scatter.add_system` immediately — no confirm dialog.
- **Once chosen, the `system_type` is LOCKED.**
- **DO NOT** implement a "Convert to Procedural" or "Convert to Manual" button. This was explicitly rejected during design because it risks being misread as a "bake" or type-conversion capability the addon does not have. The choice is made once, up front, and is permanent for that specific system object.

### Rule D: Effector List Behavior
- **No expand/collapse toggles** (`TRIA_DOWN` / `TRIA_RIGHT`) on the list items, and no `expanded` state on the effector data at all.
- The active effector's detail panel is **always shown open** by default below the list, unconditionally, to save clicks.
- The effector's name field must be editable directly in the detail panel (not just via the Outliner).
- Adding an effector opens `SCATTER_OT_add_effector_popup` (`invoke_props_dialog` + `template_icon_view`, no header/sub-header/search bar), with a footer showing the currently-highlighted effector's name (`INFO` icon) and dimmed description — updates live as the user browses before confirming.

### Rule E: Icon Safety (CRITICAL)
- Every `icon='...'` string passed to a Blender UI call **MUST** be a real, valid identifier from Blender's official icon enum.
- An invalid icon throws a silent exception mid-`draw()` and blanks out everything drawn after it in that panel (no error dialog, just missing UI).
- Before introducing a new icon name, verify it against Blender's official documentation rather than guessing what "sounds right".

### Rule F: One Object, One Ground (No Duplicates)
- A mesh object can only be registered as a Target Ground **once**, across the entire scene. This avoids ambiguity about which Ground's scatter systems "belong" to a given mesh.
- Enforced at two points:
  1. `_mesh_only_poll` (`properties.py`) — the `scatter_ground_picker_temp` object picker (used by `SCATTER_OT_add_ground_popup`) filters out any mesh already registered as a ground.
  2. `SCATTER_OT_add_ground_from_selected.poll()` (`ground_ops.py`) — grays out the button if the active object is already a registered ground.
- `SCATTER_OT_add_ground_popup.execute()` also re-checks and reports a warning as a safety net, in case the picker UI is stale.

### Rule G: Active Scatter System Selection Mirroring
- Selecting a Scatter System in the list (`SCATTER_UL_systems`) automatically selects its `curve_obj` in the viewport and Outliner, and makes it the active object — a one-way mirror from UI selection to viewport selection.
- Implemented via the `update` callback on `SCATTER_GroundItem.active_scatter_system_index` (`properties.py::_on_active_system_index_update`), not a separate operator, since `template_list` changes this index directly through property binding.
- This does **not** mirror the other direction (selecting the curve object in the viewport does not currently change the active list index) — that's a possible future addition, not yet requested.

### Rule H: Linked GeoNodes Socket Exposure
- Every socket on a linked node group (see Section 7) that gets its own control in the addon's N-panel MUST have `hide_in_modifier` checked on the node group's interface. This keeps the addon's own panel as the single point of interaction — no duplicate/conflicting control surface via Blender's native Properties > Modifier tab.
- A socket that is wired internally by the addon and never meant to be user-facing (e.g. `Target Ground`) is likewise never drawn in the N-panel — it is set once in Python at creation time (see Section 7).
- Socket identifiers (`Socket_2`, etc.) must never be hardcoded in Python. Always resolve the socket by its `name` at runtime via `node_tree.interface.items_tree`, so re-ordering or editing the node group doesn't silently break the wiring.

---

## 5. Current Implementation Status

### What is SETTLED:
- [x] Data model structure (PropertyGroups for Systems and Effectors).
- [x] UI panel layout, visual hierarchy, and compact styling.
- [x] Operator dependency chains (`poll()` logic, Rule A).
- [x] Bottom-to-top stack logic for both Systems and Effectors, incl. Move Up/Down for Effectors (Rule B).
- [x] Consistent English terminology and English-only comments across all user-facing UI and code.
- [x] Addon name: `RAF Scatter` (all-caps), reflected in `bl_info["name"]` and the main panel's `bl_label`.
- [x] Modular package structure in place and installable (see Section 6).
- [x] Effector detail panel always open, no collapse toggle (Rule D).
- [x] Inline double-click rename for both Systems and Effectors lists.
- [x] `target_ground` no longer shown in the Systems list row (still stored/used internally, Rule A intact).
- [x] Custom thumbnail loading (`utils/icons.py`) for effectors, scatter systems, and brushes — populated and confirmed working (see Section 10, CP-log).
- [x] Add Effector popup: `template_icon_view` + footer description, no header/search bar (Rule D).
- [x] Add Scatter System: simple dropdown menu, no dialog (Rule C).
- [x] Brush selector: inline `template_icon_view` bound to `scene.scatter_active_brush`, no popup, no separate `SCATTER_OT_set_brush` operator.
- [x] Delete Scatter System confirm dialog (`invoke_confirm`).
- [x] Effector layering: newest item always inserted at index 0 (Rule B).
- [x] Start/Stop Painting button restyle (`row.alert` red state, `BRUSH_DATA`/`X` icons).
- [x] Rule F (one object, one ground) and Rule G (system selection mirrors to curve object) — see Section 10 CP-log for verification status.
- [x] `resources/node_groups.blend` now exists, with the first linked node group (`gn_proceduralScatter`) authored and documented (see Section 7).

### What is PLACEHOLDER (Marked with `# TODO` in code):
- [x] `gn_proceduralScatter` GeoNodes wiring + panel controls (`utils/geonodes.py::setup_system_modifier_stack()`, `ui/panels.py::draw_procedural_controls()`) — see Section 7, CP-11.
- [ ] Real Curves sculpt mode entry/exit (`bpy.ops.object.mode_set(mode='SCULPT_CURVES')`).
- [ ] Mapping custom brush operators to Blender's native `curves_sculpt` brushes.
- [ ] Procedural distribute-on-faces logic and seed manipulation.
- [ ] Dynamic UI generation: Reading `node_tree.interface.items_tree` (Blender 4.0+ API) to generate sliders based on the linked Effector node group's input sockets (replacing the current hardcoded `density` / `scale_variance` placeholders).

---

## 6. Modular Addon Package (Active Structure)
This is the actual layout in place now, not a plan. New code goes inside this structure.

```text
raf_scatter/
├── __init__.py              # bl_info, top-level register()/unregister() routing
├── properties.py            # PropertyGroups (ScatterSystem, EffectorItem) + Scene props, Rule F/G callbacks
├── operators/
│   ├── __init__.py          # aggregates classes from the files below, routes register/unregister
│   ├── system_ops.py        # Add/Remove Scatter System (curves_empty_hair_add-based)
│   ├── effector_ops.py      # Add/Remove/Move Effectors
│   ├── ground_ops.py        # Add/Remove Target Ground, Rule F duplicate guard
│   ├── brush_ops.py         # Toggle manual mode
│   └── procedural_ops.py    # Regenerate seed
├── ui/
│   ├── __init__.py          # aggregates classes from the files below, routes register/unregister
│   ├── panels.py            # Main N-Panel (SCATTER_PT_main)
│   ├── lists.py             # UILists (Systems, Effectors)
│   └── menus.py             # Dropdown menus (Add System type picker)
├── utils/
│   ├── __init__.py
│   ├── icons.py             # Custom icon loader (preview collection) — populated, confirmed working
│   └── geonodes.py          # Helper functions to read/write node_tree interfaces (see Section 7)
└── resources/
    ├── thumbnails/           # Custom PNG thumbnails for effectors/systems/brushes — populated
    └── node_groups.blend    # Library of linked node groups (Effectors + Procedural) — see Section 7
```

**Where new work goes:**
- New operator → new file in `operators/` (or add to an existing topic file if it clearly belongs there), then list the module in `operators/__init__.py`'s `_modules` tuple. Never register a class by hand outside that routing.
- New panel/list/menu → same pattern inside `ui/`.
- Anything touching GeoNodes, node group linking, or modifier stacks → `utils/geonodes.py`. Panels and operators should call into this file, not build node trees inline.
- New scene-level or PropertyGroup fields → `properties.py` only.
- Custom icons → load them in `utils/icons.py`'s `register()`, reference via `get_icon_id()`; never hardcode a filesystem path as an `icon='...'` string.

---

## 7. Linked Node Groups (`resources/node_groups.blend`)
Node groups used by the addon's Geometry Nodes modifiers are **linked** (not appended) from this external file, so updates made to the source file can propagate without re-baking them into the addon package. Naming convention: Geometry Nodes groups meant to be linked by the addon are prefixed `gn_`.

### `gn_proceduralScatter`
Source: `resources/node_groups.blend > NodeTree > gn_proceduralScatter`. Used by `PROCEDURAL`-type Scatter Systems, set up via `utils/geonodes.py::setup_system_modifier_stack()`.

| Socket | Type | Default | Range / Options | Shown in N-panel |
| :--- | :--- | :--- | :--- | :--- |
| Target Ground | Object | — | — | No |
| Distribute | Menu | Random | Random / Poisson Disk | Yes |
| Density | Float | 10.0 | 0.0 – ∞ | Yes |
| Seed | Integer | 0 | int32 min / max | Yes |

**Wiring rules (Rule H):**
- `Target Ground` is wired once, in Python, at system creation time — resolved by socket **name**, never a hardcoded identifier — and points at the system's already-selected Target Ground. It is never drawn as a control.
+ `Distribute`, `Density`, and `Seed` are drawn directly in `ui/panels.py::draw_procedural_controls()` against the modifier's own socket values (not duplicated into a separate PropertyGroup), so there is a single source of truth for their current value. No `slider=` or other display override is applied — the socket's own subtype (set on the node group interface, Rule H) fully controls presentation (e.g. `Density`'s `None` subtype renders as a free-drag field like Transform > Scale, not a filled Factor-style bar).
- All four sockets have `hide_in_modifier` checked on the node group interface, so none of them are exposed a second time via Blender's native Properties > Modifier tab.
+ Status: implemented (see CP-11, Section 10). `setup_system_modifier_stack()` wires Target Ground + links the node group; `draw_procedural_controls()` reads Distribute/Density/Seed via `get_modifier_input_path()`.
---

## 8. Sync Workflow (Prototype File ↔ Modular Package)
The author iterates on UI/UX fast by editing the single-file prototype (`manual_scatter_addon_prototype*.py`) directly in Blender's Text Editor, then hands the updated file to an agent to port into the modular package. This is a deliberate two-track workflow, not two conflicting sources of truth. When handed a new prototype file:

1. Read it in full and diff it mentally against the current modular package — identify what's actually new, not just re-paste everything.
2. Port the change into the correct module(s) per the file map in Section 6, translating any non-English comments/strings to English per the Language Rule.
3. If anything in the new prototype file contradicts this guide, apply the **Conflict Resolution Rule** from the top of this document — ask, don't assume.
4. Once resolved, update this guide's relevant section so it stays accurate for the next session.
5. The modular package (`raf_scatter/`) is what actually gets zipped and installed — treat it as the deliverable; the prototype file is scratch space.

---

## 9. Planned Next Steps (Roadmap)
With the modular skeleton in place, the next phases are implementation, not restructuring:

1. **GeoNodes integration (`utils/geonodes.py`):** implement `setup_system_modifier_stack()`, `append_effector_to_stack()`, `read_node_group_inputs()`, wired from `system_ops.py` / `effector_ops.py`. First target: `gn_proceduralScatter` (Section 7).
2. **Dynamic effector sliders:** once `read_node_group_inputs()` works, replace the hardcoded `density`/`scale_variance` in `properties.py` and `ui/panels.py` with sockets generated from the linked node group.
3. **Real Curves sculpt mode + brush mapping** in `brush_ops.py`.

---

## 10. Vibe Coding Checkpoints

Because UI/UX is still evolving in parallel with logic implementation, this section tracks **confirmed-working checkpoints** — features the author has actually tested in Blender and confirmed correct — separate from features an agent just delivered but the author hasn't verified yet.

**Rule:** an agent may propose/implement a feature, but it only becomes a checkpoint entry after the author explicitly confirms it works. Until confirmed, treat it as "PENDING VERIFICATION" — don't build further logic on top of an unverified feature without flagging that dependency to the author first.

### Log

**CP-1: Effector popup — image-only grid → reverted to native browse pattern**
Status: CONFIRMED
What: `template_icon_view` + footer description (name/desc of highlighted item), no header/sub-header/search bar. Custom thumbnails via `utils/icons.py` preview collection.
Files: `operators/effector_ops.py`, `properties.py`

**CP-2: Effector layering — newest always on top**
Status: CONFIRMED
What: `effectors.move(len-1, 0)` after add, matching Rule B.
Files: `operators/effector_ops.py`

**CP-3: Delete Scatter System confirm dialog**
Status: CONFIRMED
What: `invoke_confirm` before deleting, same pattern as Delete Ground.
Files: `operators/system_ops.py`

**CP-4: Brush selector — inline `template_icon_view`, no popup**
Status: CONFIRMED
What: `scatter_active_brush` enum carries custom thumbnails (`brush_line`, `brush_density`, `brush_delete`, `brush_slide`), drawn inline in Manual Mode panel via `template_icon_view`. `SCATTER_OT_set_brush` operator removed.
Files: `properties.py`, `operators/brush_ops.py`, `ui/panels.py`

**CP-5: Add Scatter System — reverted to simple dropdown menu**
Status: CONFIRMED
What: `SCATTER_MT_add_system_type` menu (icon+text rows, no dialog), `scatter.add_system` executes immediately on click.
Files: `ui/menus.py`, `operators/system_ops.py`, `ui/panels.py`

**CP-6: Start/Stop Painting button restyle**
Status: CONFIRMED
What: "Start Painting"/"Stop Painting" labels, `row.alert` red state when active, icon `BRUSH_DATA`/`X`.
Files: `ui/panels.py`

**CP-7: "Add Selected as Ground" button**
Status: PENDING VERIFICATION
What: New operator, poll requires `active_object.type == 'MESH'`, grays out otherwise.
Files: `operators/ground_ops.py`, `ui/panels.py`

**CP-8: Scatter System curve creation via `curves_empty_hair_add`**
Status: PENDING VERIFICATION
What: Replaced manual `bpy.data.curves.new()` with `bpy.ops.object.curves_empty_hair_add()` for proper surface binding. Needs testing across both MANUAL and PROCEDURAL system types, and edge cases.
Files: `operators/system_ops.py`

**CP-9: Rule F — one object, one ground (no duplicates)**
Status: PENDING VERIFICATION
What: Ground picker excludes objects already registered as a ground; "Add Selected as Ground" grays out for the same reason; `execute()` re-checks as a safety net.
Files: `properties.py`, `operators/ground_ops.py`

**CP-10: Rule G — active system selection mirrors to curve object**
Status: PENDING VERIFICATION
What: Clicking a Scatter System in the list selects its `curve_obj` in the viewport/Outliner via `update` callback on `active_scatter_system_index`.
Files: `properties.py`

**CP-11: Procedural modifier stack — GeoNodes wiring + panel controls**
Status: PENDING VERIFICATION
What: `setup_system_modifier_stack()` links `gn_proceduralScatter`, wires Target Ground by socket name; `draw_procedural_controls()` draws Distribute/Density/Seed against modifier's own values; `Regenerate` button bumps Seed. Includes `_deduplicate_surface_deform()` (single Surface Deform modifier across repeated Add System / undo-redo) — author-confirmed working.
Files: `utils/geonodes.py`, `ui/panels.py`, `operators/procedural_ops.py`

**CP-12: Procedural panel — removed forced slider=True on Density**
Status: CONFIRMED (author-verified: slider param was overriding the node group's None subtype with Factor-style bar rendering)
What: `col.prop(modifier, prop_path, text=socket_name)` — no display overrides; socket subtype from the node group interface is the single source of truth for how each control renders.
Files: `ui/panels.py`