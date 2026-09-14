# HY3D gateway protocol v0.1

The client speaks a project-defined gateway protocol. Hunyuan3D deployments differ;
an upstream server is **not assumed** to implement these routes. No inference server
or model weights are bundled. A compatible adapter is a separate integration task.

Configuration is outside the manifest: `type` is `local`, `remote`, or `ssh`. For direct HTTP(S), `endpoint`
is the base URL, `timeout_s` defaults to 300, and optional `token_env` names an
environment variable. Direct remote connections require HTTPS. Redirects are rejected.
The client performs no automatic expensive retries.

For the selected SSH deployment, use [configs/hy3d_ssh.yaml](../configs/hy3d_ssh.yaml).
The endpoint is derived from `ssh.local_port`. Each real HTTP request opens a managed
OpenSSH tunnel to `127.0.0.1:<remote_port>` on the GPU server, then closes its own SSH
process on completion or failure. Inference remains on that server. The client refuses
an occupied local forwarding port rather than connecting to an unrelated local service.
Loopback HTTP bypasses HTTP proxy environment settings. See [connection workflow](mcp_and_ssh.md).

The tunnel does not install HY3D or translate native model APIs. The supplied deployment
report records Hunyuan3D-2.1 environment and weights prepared, but no API service started.
A matching gateway adapter and real inference validation are still pending.
`ssh-check` inspects connectivity/GPU details, while `hy3d-health` tests this
gateway protocol; neither is proof of successful inference.

When `token_env` is configured, its environment variable must be nonempty, including
for health checks. The client sends `Authorization: Bearer <token>`. An explicitly
unauthenticated gateway requires omitting `token_env`; an empty value is not an opt-out.

`GET /health` returns:

```json
{"status":"ok","capabilities":["generate_shape","generate_textured_asset","retexture_mesh"]}
```

`POST /v1/<capability>` accepts:

```json
{
  "prompt": "An isolated stylized station bench",
  "reference_images": [{"name":"front.png","data_base64":"..."}],
  "style_bible": {"visual_style":{"target":"restrained_stylized"}},
  "seed": 0,
  "mesh": {"name":"original.glb","data_base64":"..."}
}
```

`mesh` is supplied only for retexture. Reference images may be empty if the adapter
can handle text input. Unsupported text input must return an error, not silently
ignore the prompt. The backend must implement any text-to-image preparation needed
by its model. The response is a JSON object with `model_base64` containing a complete
embedded glTF 2.0 GLB. Return non-2xx on failure. Input files are bounded to 64 MiB
each; HTTP responses to 256 MiB. Synchronous jobs that exceed the timeout fail and
require inspection of backend status before a new revision is requested.

The client does not poll asynchronous job IDs or fetch returned URLs/server paths.
A gateway wrapping an asynchronous backend must wait for completion and return the
embedded GLB within the configured timeout, or the client contract needs a separately
governed extension. Advertise only operations actually implemented by the adapter.

Route C also requires `output_source` in the configuration, with all the source
fields defined in the stage1_result schema: provider, asset_id, original_url,
creator, license, license_verified, attribution_required, modification_allowed.
Set these based on the actual backend's terms; there is no default claim that
generated outputs are CC0. The MVP accepts verified `cc0` or `cc_by` output rights.
Broader license support requires an explicit policy extension.

The saved recipe records prompt, seed, operation, backend type, reference checksums,
style checksum, and original mesh checksum where applicable. Determinism still
depends on the gateway/model version. Tokens and request headers are never saved.
Phase 1 supports B1 retexture; rendered-view regeneration and geometry adaptation
are not implemented.
