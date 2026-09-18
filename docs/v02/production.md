# Separated Blender production

After approved geometry, author four documents: blockout_plan (meter placement, rotation in degrees, positive scale, local parent hierarchy, repetition and local spacing), semantic_material_map (material class/condition), lookdev_plan (style-linked lighting and atmosphere), render_plan (camera, engine, resolution, samples, color and PNG path).

`scene-plans-submit PROJECT --plans PLANS.yaml --expected-version VERSION` persists the four contracts and enters blockout_pending. While that state remains pending, visual-only revisions may increment material/lookdev/render revisions while retaining the exact blockout document. This supports reviewable adjustments before completing setup; later changes use the reviewed revision flow.

`scene-prepare PROJECT` returns a guarded, machine-specific MCP packet and explicit operation names. Execute runtime/blender_operations.py run(packet_path, expected_sha256, operation) in order:

- asset.import: acquire geometry into an isolated scene, or reuse the matching existing geometry.
- asset.place: apply spatial layout and record a geometry fingerprint.
- material.assign_semantic: assign the resolved six-class library material and condition.
- lighting.apply_profile / atmosphere.apply_profile: apply selected environment settings.
- camera.apply_profile: set camera, engine and color settings; save a real setup blend and receipt.
- render.preview: render a new PNG explicitly. Queue via Blender timer for MCP responsiveness and inspect completion; queued is not successful.

The first version supports one body material slot per object. Split semantic objects during planning when different parts need different classes. Non-null surface_source requests reject because texture blending is not implemented yet; retained original/paint sources are not silently treated as final materials. The runtime supports Cycles and Eevee, defaults to the selected profile, and requires exact registered semantic operations. Batch is not an automatic fallback.

Input guards include the manifest, current documents, geometry/surface files, style resources and worker code. Regenerate packets on another machine or after input changes. Changes to the evaluated mesh topology, vertex positions or world transforms invalidate the geometry fingerprint. Material/light/camera operations cannot pass by altering geometry. The active user scene is restored after every operation.

`scene-setup-complete PROJECT --packet PACKET --sha256 HASH` verifies current inputs, actual blend bytes and matching before/after geometry receipt, then records completed blockout/lookdev and enters render_pending through ManifestManager. It grants no visual approval. Actual preview metadata is recorded through preview-complete.

使用外部视觉导演时，参阅 [Render Director 接入](render-director.md)。
