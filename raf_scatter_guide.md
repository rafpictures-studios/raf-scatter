# Raf Scatter — AI Agent & Developer Guide

> **⚠️ CRITICAL INSTRUCTIONS FOR AI AGENTS / CODING ASSISTANTS:**
> Read this document entirely before generating, refactoring, or modifying any code for this project. This addon has strict UI/UX preferences, a rigid dependency chain, and a modular architecture that is now the active baseline (see Section 1).
> - **NEVER guess Blender icon names.** Invalid icons will silently throw an exception mid-`draw()` and blank out the rest of the UI panel. Always verify against Blender's official icon enum.
> - **NEVER add a "Convert" or "Change Type" feature** for Scatter Systems (Manual/Procedural). The choice is strictly irreversible once made.
> - **Keep UI drawing decoupled** from data models and operator logic to allow future viewport/gizmo integrations and custom icon swapping without breaking core functionality.
> - **Language Rule:** ALL text in this codebase MUST be in English — this includes user-facing UI text (labels, button texts, tooltips, popup messages) AND code comments/docstrings. No exceptions, no dev-facing Indonesian notes. Keep comments short and only where they add real value; avoid long or frequent comment blocks — a single concise line beats a paragraph. (This supersedes any earlier version of this guide that allowed Indonesian comments.)
> - **Conflict Resolution Rule:** if anything in a newly uploaded/pasted code file contradicts this guide, DO NOT silently pick one side. Flag the conflict explicitly to the user and ask which one is correct before proceeding. Once the user decides, update this guide to match — the guide must never be allowed to drift out of sync with the actual codebase.
> - **Edit Mode:** once the modular package exists (it does, see Section 1), prefer targeted edits — per file, per function/class — over regenerating whole files from scratch, unless the user explicitly asks for a full rewrite or a file is trivially short. This keeps diffs reviewable and avoids silently overwriting settled work.

---

## 1. Project Overview
A custom Blender addon that allows users to scatter points onto a target surface—either manually using sculpt-style brushes or procedurally—and then modify the distribution through a stack of Geometry Nodes-driven "Effectors".

- **Addon Name (Finalized):** `RAF Scatter` (all-caps RAF, updated from `Raf Scatter` per author feedback — see Section 5 changelog). Chosen over "eco"/"ecosystem"-based names because those terms are already heavily used as generic feature descriptors by existing competitors (OpenScatter, Eco-Scatter, Ecosystem Generator), risking brand confusion with existing marketplace products. "Ecosystem" is retained only as a **tagline** — e.g. *"RAF Scatter — Ecosystem scattering toolkit for Blender"* — not as part of the product name itself.
- **Current State:** Dual-track development.
  1. **`raf_scatter/` — the modular addon package.** This is the actual installable addon and the source of truth for anything beyond fast visual iteration: `__init__.py`, `properties.py`, `operators/`, `ui/`, `utils/`, `resources/`. This is the starting point for any agent picking up work — do not propose re-flattening it back into a single file.
  2. **`manual_scatter_addon_prototype*.py` — a single-file UI/UX sketchpad.** Used by the author for fast visual/interaction iteration (paste into Blender Text Editor, Alt+P, no addon install/reload cycle needed). Not the source of truth once a change is confirmed — see Section 7, Sync Workflow.
- **Target State:** A fully modular, professional-grade Blender addon package (`raf_scatter`) with custom icons, dynamic GeoNodes integration, and viewport overlays. The package skeleton for this already exists (see Section 6); remaining work is filling in the GeoNodes/icon TODOs, not restructuring.

---

## 2. Author's Goals & Design Philosophy
- **Modular Architecture:** Done — see Section 6 for the actual layout now in place. Keep new code inside this structure rather than growing any single file too large.
- **Heavy Customization Ready:** Expect future requests for custom icons, UI polish, and viewport-level adjustments (gizmos, overlays). Build with this in mind: keep UI drawing, data models, and operator logic loosely coupled.
- **Design Taste:** Minimalist, compact, and "proper" Blender-native UI. Avoid flashy or non-standard layouts. Use icon-first compact rows over wide text buttons. Use `box()` *only* to group Lists + Toolbars, not for every single section. Use small section headers (icon + label, via a shared `draw_section_header()` helper) for everything else. Use `layout.separator(factor=...)` sparingly for breathing room — favor a few well-placed separators over one after every block.
- **Inline Rename:** Both list UIs (`SCATTER_UL_systems`, `SCATTER_UL_effectors`) support Blender's native double-click-to-rename, by drawing `name` via `row.prop(item, "name", text="", emboss=False)` instead of `row.label()` — same pattern as the Outliner.
- **Minimal List Rows:** `SCATTER_UL_systems` shows only name + type icon. It intentionally does **not** display `target_ground` in the row (removed per author feedback) — `target_ground` is still stored on the PropertyGroup and used internally (Rule A dependency, curve object naming), just not surfaced in the list.

---

## 3. Terminology (Do Not Drift From This)
| Term | Meaning & Context |
| :--- | :--- |
| **Target Surface** | The mesh object a scatter system's Curves object attaches to. This is **Step 1** of the whole system. Nothing else can exist without it. (Renamed from "Target Ground" to match Blender's native terminology). |
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
- Reordering via `Move Up` / `Move Down` is implemented for **Effectors** (`SCATTER_OT_move_effector` in `operators/effector_ops.py`, wired in `ui/panels.py::draw_effectors`). The buttons sit below Add/Remove separated by a small UI gap (matching Blender's native modifier stack pattern). "Up" moves towards index 0 (top of stack), "Down" moves towards the end.
- Scatter Systems do **not** have Move Up/Down — there is no user-facing need to manually reorder systems relative to each other, only newest-on-top on creation.

### Rule C: Irreversible Scatter System Creation
- Clicking "+" on the Scatter System list opens a small dropdown menu: Manual or Procedural.
- **Once chosen, the `system_type` is LOCKED.**
- **DO NOT** implement a "Convert to Procedural" or "Convert to Manual" button. This was explicitly rejected during design because it risks being misread as a "bake" or type-conversion capability the addon does not have. The choice is made once, up front, and is permanent for that specific system object.

### Rule D: Effector List Behavior
- **No expand/collapse toggles** (`TRIA_DOWN` / `TRIA_RIGHT`) on the list items, and no `expanded` state on the effector data at all.
- The active effector's detail panel is **always shown open** by default below the list, unconditionally, to save clicks.
- The effector's name field must be editable directly in the detail panel (not just via the Outliner) — currently a plain text field at the top of the detail panel.

### Rule E: Icon Safety (CRITICAL)
- Every `icon='...'` string passed to a Blender UI call **MUST** be a real, valid identifier from Blender's official icon enum.
- An invalid icon throws a silent exception mid-`draw()` and blanks out everything drawn after it in that panel (no error dialog, just missing UI).
- Before introducing a new icon name, verify it against Blender's official documentation rather than guessing what "sounds right".

---

## 5. Current Implementation Status

### What is SETTLED:
- [x] Data model structure (PropertyGroups for Systems and Effectors).
- [x] UI panel layout, visual hierarchy, and compact styling (section headers, `grid_flow` brush row, box only around list+toolbar areas).
- [x] Operator dependency chains (`poll()` logic).
- [x] Bottom-to-top stack logic (Move Up/Down operators still pending, see Rule B).
- [x] Consistent English terminology and English-only comments across all user-facing UI and code.
- [x] Addon name: `Raf Scatter`.
- [x] Per-brush tooltips via `Operator.description()` (icon-only buttons stay accessible).
- [x] Modular package structure in place and installable (see Section 6).
- [x] Effector detail panel always open, no collapse toggle (Rule D, no `expanded` property).
- [x] Move Up / Move Down effector operators (Rule B) — `SCATTER_OT_move_effector`.
- [x] Scatter Systems now use bottom-to-top stack order on creation, mirroring Effectors (Rule B).
- [x] Inline double-click rename for both Systems and Effectors lists.
- [x] `target_ground` no longer shown in the Systems list row (still stored/used internally, Rule A intact).
- [x] Addon name updated to `RAF Scatter` (all-caps), reflected in `bl_info["name"]` and the main panel's `bl_label`.

### What is PLACEHOLDER (Marked with `# TODO` in code):
- [ ] Actual Geometry Nodes modifier stack generation on the Curves object (`utils/geonodes.py`).
- [ ] Real Curves sculpt mode entry/exit (`bpy.ops.object.mode_set(mode='SCULPT_CURVES')`).
- [ ] Mapping custom brush operators to Blender's native `curves_sculpt` brushes.
- [ ] Procedural distribute-on-faces logic and seed manipulation.
- [ ] Dynamic UI generation: Reading `node_tree.interface.items_tree` (Blender 4.0+ API) to generate sliders based on the linked Effector node group's input sockets (replacing the current hardcoded `density` / `scale_variance` placeholders).
- [ ] Custom icon loading (`utils/icons.py` — preview collection is wired up but nothing is loaded into it yet).
- [ ] `resources/node_groups.blend` does not exist yet.

---

## 6. Modular Addon Package (Active Structure)
This is the actual layout in place now, not a plan. New code goes inside this structure.

```text
raf_scatter/
├── __init__.py              # bl_info, top-level register()/unregister() routing
├── properties.py            # PropertyGroups (ScatterSystem, EffectorItem) + Scene props
├── operators/
│   ├── __init__.py          # aggregates classes from the files below, routes register/unregister
│   ├── system_ops.py        # Add/Remove Scatter System
│   ├── effector_ops.py      # Add/Remove Effectors (Move Up/Down: TODO)
│   ├── brush_ops.py         # Toggle manual mode, Set Brush, BRUSH_ICONS/BRUSH_TOOLTIPS
│   └── procedural_ops.py    # Regenerate seed
├── ui/
│   ├── __init__.py          # aggregates classes from the files below, routes register/unregister
│   ├── panels.py            # Main N-Panel (SCATTER_PT_main)
│   ├── lists.py             # UILists (Systems, Effectors)
│   └── menus.py             # Dropdown menus (Add System type picker)
├── utils/
│   ├── __init__.py
│   ├── icons.py             # Custom icon loader (preview collection) — not yet populated
│   └── geonodes.py          # Stub helper functions to read/write node_tree interfaces
└── resources/
    ├── icons/                # Custom SVG/PNG icons — empty for now
    └── node_groups.blend    # Library of linked Effector node groups — does not exist yet
```

**Where new work goes:**
- New operator → new file in `operators/` (or add to an existing topic file if it clearly belongs there), then list the module in `operators/__init__.py`'s `_modules` tuple. Never register a class by hand outside that routing.
- New panel/list/menu → same pattern inside `ui/`.
- Anything touching GeoNodes, node group linking, or modifier stacks → `utils/geonodes.py`. Panels and operators should call into this file, not build node trees inline.
- New scene-level or PropertyGroup fields → `properties.py` only.
- Custom icons → load them in `utils/icons.py`'s `register()`, reference via `get_icon_id()`; never hardcode a filesystem path as an `icon='...'` string.

---

## 7. Sync Workflow (Prototype File ↔ Modular Package)
The author iterates on UI/UX fast by editing the single-file prototype (`manual_scatter_addon_prototype*.py`) directly in Blender's Text Editor, then hands the updated file to an agent to port into the modular package. This is a deliberate two-track workflow, not two conflicting sources of truth. When handed a new prototype file:

1. Read it in full and diff it mentally against the current modular package — identify what's actually new (data model change, new operator, visual/UX pass, etc.), not just re-paste everything.
2. Port the change into the correct module(s) per the file map in Section 6, translating any Indonesian comments/strings to English per the Language Rule.
3. If anything in the new prototype file contradicts this guide (e.g. an `expanded` toggle reappearing after Rule D said it shouldn't exist), apply the **Conflict Resolution Rule** from the top of this document — ask, don't assume.
4. Once resolved, update this guide's relevant section (Rule, Section 5 status, or Section 6 file map) so it stays accurate for the next session.
5. The modular package (`raf_scatter/`) is what actually gets zipped and installed — treat it as the deliverable; the prototype file is scratch space.

---

## 8. Planned Next Steps (Roadmap)
With the modular skeleton in place, the next phases are implementation, not restructuring:

1. **GeoNodes integration (`utils/geonodes.py`):** implement `setup_system_modifier_stack()`, `append_effector_to_stack()`, `read_node_group_inputs()`, wired from `system_ops.py` / `effector_ops.py`.
2. **Dynamic effector sliders:** once `read_node_group_inputs()` works, replace the hardcoded `density`/`scale_variance` in `properties.py` and `ui/panels.py` with sockets generated from the linked node group.
3. **Real Curves sculpt mode + brush mapping** in `brush_ops.py`.
4. **Custom icons** via `utils/icons.py`, once `resources/icons/` actually has assets.
