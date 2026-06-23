# This project was developed with assistance from AI tools.
"""Phase-1 warehouse scenario — Nucleus scene + Kafka twin-update.

Opens the customized warehouse scene from Nucleus. Subscribes to
fleet.telemetry and fleet.safety.alerts on background threads; prim updates
are queued and applied on Kit's main-thread update tick.

Chains viewport_mjpeg.py for the MJPEG viewport broadcaster and sets a
static camera position for the demo viewpoint.

Env contract:
    SCENE_PACK_URL          — omniverse:// URL of the warehouse scene on Nucleus
    NUCLEUS_USER            — Nucleus auth user (default "omniverse")
    NUCLEUS_PASS            — Nucleus auth password
    KAFKA_BOOTSTRAP_SERVERS — Kafka bootstrap (default fleet-kafka-bootstrap.fleet-ops.svc:9092)
    KAFKA_SECURITY_PROTOCOL — PLAINTEXT (default) or SSL
"""

import asyncio
import json
import math
import os
import queue
import threading
import time
import traceback
import uuid

import carb
import omni.kit.app
import omni.timeline
import omni.usd

SCENE_PACK_URL = os.environ.get("SCENE_PACK_URL", "")
NUCLEUS_USER = os.environ.get("NUCLEUS_USER", "omniverse")
NUCLEUS_PASS = os.environ.get("NUCLEUS_PASS", "")

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "fleet-kafka-bootstrap.fleet-ops.svc:9092")
KAFKA_SECURITY_PROTOCOL = os.environ.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")

FORKLIFT_PRIM = "/Root/Warehouse/Assets/forklift"
FORKLIFT_START = (-22.82, 5.8, 0.0)
FORKLIFT_ROT_Z = 90.0

OBSTRUCTION_PRIMS = [
    "/Root/Warehouse/Assets/SM_PaletteA_3218/SM_PaletteA_01",
    "/Root/Warehouse/Assets/Box_19583/SM_CardBoxA_02",
    "/Root/Warehouse/Assets/Box_19581/SM_CardBoxD_03",
]
FALLEN_POSES = [
    ((-1.18085, 0.0, -2.5), (-2.441, -34.975, -1.4)),
    ((-2.56227, -1.87009, -2.65), (-69.77561, -86.7106, 208.01714)),
    ((-3.0, 0.0, -3.01), (0.0, 0.0, -52.0)),
]

ROUTE_PATH_PRIM = "/Root/route_display"
ROUTE_PATH_HEIGHT = 0.02
ROUTE_STRIP_WIDTH = 0.25

ROUTE_WAYPOINTS = {
    "aisle-3": [
        (-22.82, 5.8,   ROUTE_PATH_HEIGHT),
        (-13,    5.8,   ROUTE_PATH_HEIGHT),
        (-13,    27.57, ROUTE_PATH_HEIGHT),
        (4.284,  27.57, ROUTE_PATH_HEIGHT),
    ],
    "aisle-4": [
        (-22.82, 5.8,   ROUTE_PATH_HEIGHT),
        (-8,     5.8,   ROUTE_PATH_HEIGHT),
        (-8,     27.57, ROUTE_PATH_HEIGHT),
        (4.284,  27.57, ROUTE_PATH_HEIGHT),
    ],
}

ROUTE_COLORS = {
    "dispatch": (0.0, 0.7, 1.0),
    "reroute": (0.0, 0.7, 1.0),
}

_CMD_QUEUE: "queue.Queue[tuple]" = queue.Queue(maxsize=64)

# ---- Diagnostics state ------------------------------------------------------
_diag_telemetry_recv = 0
_diag_telemetry_enqueued = 0
_diag_telemetry_dropped = 0
_diag_telemetry_last_ts = 0.0
_diag_alert_recv = 0
_diag_alert_enqueued = 0
_diag_update_tick = 0
_diag_moves_applied = 0
_diag_obstruction_cmds = 0
_diag_resets = 0
_diag_queue_drain_total = 0
_diag_last_report_ts = 0.0
_DIAG_REPORT_INTERVAL = 10.0

_AUTH_SUB = None
_UPDATE_SUB = None
_CAMERA_SUB = None
_forklift_translate_op = None
_forklift_rotate_op = None

_lerp_from_pos = None
_lerp_from_yaw = 0.0
_lerp_to_pos = None
_lerp_to_yaw = 0.0
_lerp_t = 1.0
_lerp_speed = 0.0

_original_xforms: dict[str, "Gf.Matrix4d"] = {}


# ---------------------------------------------------------------------------
# Nucleus auth
# ---------------------------------------------------------------------------

def _register_nucleus_auth() -> None:
    import omni.client

    def _cb(url: str):
        return (NUCLEUS_USER, NUCLEUS_PASS)

    global _AUTH_SUB
    _AUTH_SUB = omni.client.register_authentication_callback(_cb)
    carb.log_info(f"warehouse_baseline: nucleus auth registered (user={NUCLEUS_USER})")


# ---------------------------------------------------------------------------
# Scene loading
# ---------------------------------------------------------------------------

CDN_WAREHOUSE_REL = "/Isaac/Samples/Replicator/Stage/full_warehouse_worker_and_anim_cameras.usd"


async def _open_scene() -> None:
    ctx = omni.usd.get_context()

    if SCENE_PACK_URL:
        carb.log_info(f"warehouse_baseline: opening scene {SCENE_PACK_URL}")
        result, err = await ctx.open_stage_async(SCENE_PACK_URL)
        if not result:
            raise RuntimeError(f"failed to open scene: {err}")
        carb.log_info("warehouse_baseline: scene opened")
        return

    from isaacsim.storage.native import get_assets_root_path_async
    asset_root = await get_assets_root_path_async()
    if not asset_root:
        raise RuntimeError("no Isaac asset root resolved and SCENE_PACK_URL not set")
    url = f"{asset_root}{CDN_WAREHOUSE_REL}"
    carb.log_info(f"warehouse_baseline: SCENE_PACK_URL not set — falling back to CDN: {url}")
    result, err = await ctx.open_stage_async(url)
    if not result:
        raise RuntimeError(f"failed to open CDN stage: {err}")


# ---------------------------------------------------------------------------
# Kafka consumers (daemon threads)
# ---------------------------------------------------------------------------

_SESSION_ID = uuid.uuid4().hex[:8]


def _make_consumer_conf(group_id: str) -> dict:
    conf = {
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": f"{group_id}-{_SESSION_ID}",
        "auto.offset.reset": "latest",
        "enable.auto.commit": True,
    }
    if KAFKA_SECURITY_PROTOCOL != "PLAINTEXT":
        conf["security.protocol"] = KAFKA_SECURITY_PROTOCOL
        conf["ssl.endpoint.identification.algorithm"] = "none"
        conf["enable.ssl.certificate.verification"] = False
    return conf


def _telemetry_consumer() -> None:
    """Consume fleet.telemetry → queue forklift pose updates."""
    global _diag_telemetry_recv, _diag_telemetry_enqueued, _diag_telemetry_dropped, _diag_telemetry_last_ts
    try:
        from confluent_kafka import Consumer
    except ImportError:
        carb.log_warn("warehouse_baseline: confluent_kafka unavailable — telemetry subscriber disabled")
        return

    c = Consumer(_make_consumer_conf("isaac-sim-twin"))
    c.subscribe(["fleet.telemetry"])
    carb.log_info("warehouse_baseline: telemetry consumer started")

    while True:
        msg = c.poll(1.0)
        if msg is None or msg.error():
            continue
        _diag_telemetry_recv += 1
        now = time.monotonic()
        gap = now - _diag_telemetry_last_ts if _diag_telemetry_last_ts > 0 else 0
        _diag_telemetry_last_ts = now
        try:
            data = json.loads(msg.value())
            pose = data.get("pose")
            if pose:
                try:
                    _CMD_QUEUE.put_nowait(("move", FORKLIFT_PRIM, pose))
                    _diag_telemetry_enqueued += 1
                except queue.Full:
                    _diag_telemetry_dropped += 1
                    if _diag_telemetry_dropped % 20 == 1:
                        print(f"[baseline_diag] telemetry CMD_QUEUE full, dropped #{_diag_telemetry_dropped} (qsize={_CMD_QUEUE.qsize()})", flush=True)
                if _diag_telemetry_recv % 50 == 0:
                    print(
                        f"[baseline_diag] telemetry: {_diag_telemetry_recv} recv, {_diag_telemetry_enqueued} enqueued, "
                        f"{_diag_telemetry_dropped} dropped, gap={gap*1000:.0f}ms, qsize={_CMD_QUEUE.qsize()}",
                        flush=True,
                    )
        except (json.JSONDecodeError, ValueError):
            pass


def _alerts_consumer() -> None:
    """Consume fleet.safety.alerts → queue pallet show/hide."""
    global _diag_alert_recv, _diag_alert_enqueued
    try:
        from confluent_kafka import Consumer
    except ImportError:
        carb.log_warn("warehouse_baseline: confluent_kafka unavailable — alerts subscriber disabled")
        return

    c = Consumer(_make_consumer_conf("isaac-sim-twin-alerts"))
    c.subscribe(["fleet.safety.alerts"])
    carb.log_info("warehouse_baseline: alerts consumer started")

    while True:
        msg = c.poll(1.0)
        if msg is None or msg.error():
            continue
        _diag_alert_recv += 1
        try:
            data = json.loads(msg.value())
            obstructed = data.get("obstructed", False)
            print(f"[baseline_diag] alert received: obstructed={obstructed}, aisle={data.get('aisle_id')}, trace={data.get('trace_id','?')[:8]}", flush=True)
            try:
                _CMD_QUEUE.put_nowait(("obstruction", obstructed))
                _diag_alert_enqueued += 1
            except queue.Full:
                print(f"[baseline_diag] ALERT CMD_QUEUE FULL — dropped obstruction={obstructed}", flush=True)
        except (json.JSONDecodeError, ValueError):
            pass


def _missions_consumer() -> None:
    """Consume fleet.missions → queue route-path visualisation commands."""
    try:
        from confluent_kafka import Consumer
    except ImportError:
        carb.log_warn("warehouse_baseline: confluent_kafka unavailable — missions subscriber disabled")
        return

    c = Consumer(_make_consumer_conf("isaac-sim-twin-missions"))
    c.subscribe(["fleet.missions"])
    carb.log_info("warehouse_baseline: missions consumer started")

    while True:
        msg = c.poll(1.0)
        if msg is None or msg.error():
            continue
        try:
            data = json.loads(msg.value())
            kind = data.get("kind", "")
            route_aisle = data.get("params", {}).get("route_aisle", "")
            if kind in ("dispatch", "reroute") and route_aisle:
                try:
                    _CMD_QUEUE.put_nowait(("path", route_aisle, kind))
                except queue.Full:
                    pass
                print(
                    f"[baseline_diag] mission received: kind={kind}, route={route_aisle}",
                    flush=True,
                )
        except (json.JSONDecodeError, ValueError):
            pass


# ---------------------------------------------------------------------------
# Route-path visualisation helpers (called from main Kit thread only)
# ---------------------------------------------------------------------------

def _create_route_path(stage, route_aisle: str, mission_kind: str) -> None:
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    waypoints = ROUTE_WAYPOINTS.get(route_aisle)
    if not waypoints:
        return

    color = ROUTE_COLORS.get(mission_kind, ROUTE_COLORS["dispatch"])
    half_w = ROUTE_STRIP_WIDTH / 2.0

    _remove_route_path(stage)

    verts = []
    face_vert_counts = []
    face_vert_indices = []

    for i in range(len(waypoints) - 1):
        ax, ay, az = waypoints[i]
        bx, by, bz = waypoints[i + 1]

        dx, dy = bx - ax, by - ay
        length = math.sqrt(dx * dx + dy * dy)
        if length < 1e-6:
            continue
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux

        if i > 0:
            ax -= ux * half_w
            ay -= uy * half_w
        if i < len(waypoints) - 2:
            bx += ux * half_w
            by += uy * half_w

        base = len(verts)
        verts.extend([
            Gf.Vec3f(ax + nx * half_w, ay + ny * half_w, az),
            Gf.Vec3f(ax - nx * half_w, ay - ny * half_w, az),
            Gf.Vec3f(bx - nx * half_w, by - ny * half_w, bz),
            Gf.Vec3f(bx + nx * half_w, by + ny * half_w, bz),
        ])
        face_vert_counts.append(4)
        face_vert_indices.extend([base, base + 1, base + 2, base + 3])

    UsdGeom.Scope.Define(stage, ROUTE_PATH_PRIM)

    mesh = UsdGeom.Mesh.Define(stage, f"{ROUTE_PATH_PRIM}/strip")
    mesh.GetPointsAttr().Set(Vt.Vec3fArray(verts))
    mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray(face_vert_counts))
    mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray(face_vert_indices))
    mesh.GetDoubleSidedAttr().Set(True)

    mat_path = f"{ROUTE_PATH_PRIM}/material"
    mat = UsdShade.Material.Define(stage, mat_path)
    shader = UsdShade.Shader.Define(stage, f"{mat_path}/shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.85)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
    mat.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI(mesh.GetPrim()).Bind(mat)

    print(
        f"[baseline_diag] route path: {route_aisle} ({mission_kind}), "
        f"{len(verts)} verts, color={color}",
        flush=True,
    )


def _remove_route_path(stage) -> None:
    prim = stage.GetPrimAtPath(ROUTE_PATH_PRIM)
    if prim and prim.IsValid():
        stage.RemovePrim(ROUTE_PATH_PRIM)


# ---------------------------------------------------------------------------
# Main-thread prim updater (Kit update tick)
# ---------------------------------------------------------------------------

def _shortest_yaw(a: float, b: float) -> float:
    """Return delta from a to b via the shortest arc (handles wraparound)."""
    d = (b - a) % 360.0
    if d > 180.0:
        d -= 360.0
    return d


def _apply_updates(_event) -> None:
    """Drain command queue, interpolate forklift, update USD prims."""
    global _diag_update_tick, _diag_moves_applied, _diag_obstruction_cmds
    global _diag_resets, _diag_queue_drain_total, _diag_last_report_ts

    try:
        from pxr import Gf, UsdGeom
    except Exception:
        return

    stage = omni.usd.get_context().get_stage()
    if stage is None:
        return

    global _forklift_translate_op, _forklift_rotate_op
    global _lerp_from_pos, _lerp_from_yaw, _lerp_to_pos, _lerp_to_yaw
    global _lerp_t, _lerp_speed

    _diag_update_tick += 1

    TELEMETRY_HZ = 5.0
    KIT_HZ_ESTIMATE = 60.0
    LERP_STEP = TELEMETRY_HZ / KIT_HZ_ESTIMATE

    latest_move = None
    obstruction_cmds = []
    path_cmds = []
    drained = 0
    while not _CMD_QUEUE.empty():
        try:
            cmd = _CMD_QUEUE.get_nowait()
            drained += 1
        except queue.Empty:
            break
        if cmd[0] == "move":
            latest_move = cmd
        elif cmd[0] == "path":
            path_cmds.append(cmd)
        else:
            obstruction_cmds.append(cmd)
    _diag_queue_drain_total += drained

    if latest_move is not None:
        _diag_moves_applied += 1
        _, prim_path, pose = latest_move
        new_pos = Gf.Vec3d(
            float(pose.get("x", 0)),
            float(pose.get("y", 0)),
            float(pose.get("z", 0)),
        )
        new_yaw = float(pose.get("yaw", FORKLIFT_ROT_Z))

        if _lerp_to_pos is not None:
            _lerp_from_pos = Gf.Vec3d(
                _lerp_from_pos[0] + (_lerp_to_pos[0] - _lerp_from_pos[0]) * min(_lerp_t, 1.0),
                _lerp_from_pos[1] + (_lerp_to_pos[1] - _lerp_from_pos[1]) * min(_lerp_t, 1.0),
                _lerp_from_pos[2] + (_lerp_to_pos[2] - _lerp_from_pos[2]) * min(_lerp_t, 1.0),
            )
            _lerp_from_yaw = _lerp_from_yaw + _shortest_yaw(_lerp_from_yaw, _lerp_to_yaw) * min(_lerp_t, 1.0)
        else:
            _lerp_from_pos = new_pos
            _lerp_from_yaw = new_yaw

        _lerp_to_pos = new_pos
        _lerp_to_yaw = new_yaw
        _lerp_t = 0.0

        if _forklift_translate_op is None:
            prim = stage.GetPrimAtPath(prim_path)
            if prim and prim.IsValid():
                xformable = UsdGeom.Xformable(prim)
                xformable.ClearXformOpOrder()
                _forklift_translate_op = xformable.AddTranslateOp()
                _forklift_translate_op.Set(new_pos)
                _forklift_rotate_op = xformable.AddRotateXYZOp()
                _forklift_rotate_op.Set(Gf.Vec3f(0, 0, new_yaw))

    if _lerp_to_pos is not None and _lerp_t < 1.0 and _forklift_translate_op is not None:
        _lerp_t = min(_lerp_t + LERP_STEP, 1.0)
        t = _lerp_t
        cur_pos = Gf.Vec3d(
            _lerp_from_pos[0] + (_lerp_to_pos[0] - _lerp_from_pos[0]) * t,
            _lerp_from_pos[1] + (_lerp_to_pos[1] - _lerp_from_pos[1]) * t,
            _lerp_from_pos[2] + (_lerp_to_pos[2] - _lerp_from_pos[2]) * t,
        )
        cur_yaw = _lerp_from_yaw + _shortest_yaw(_lerp_from_yaw, _lerp_to_yaw) * t
        try:
            _forklift_translate_op.Set(cur_pos)
            _forklift_rotate_op.Set(Gf.Vec3f(0, 0, cur_yaw))
        except Exception:
            _forklift_translate_op = None
            _forklift_rotate_op = None

    for cmd in obstruction_cmds:
        if cmd[0] != "obstruction":
            continue
        obstructed = cmd[1]
        _diag_obstruction_cmds += 1

        if obstructed:
            for i, prim_path in enumerate(OBSTRUCTION_PRIMS):
                prim = stage.GetPrimAtPath(prim_path)
                if not prim or not prim.IsValid():
                    carb.log_warn(f"warehouse_baseline: obstruction prim missing: {prim_path}")
                    continue
                pos, rot = FALLEN_POSES[i]
                xformable = UsdGeom.Xformable(prim)
                xformable.ClearXformOpOrder()
                xformable.AddTranslateOp().Set(Gf.Vec3d(*pos))
                xformable.AddRotateXYZOp().Set(Gf.Vec3f(*rot))
                xformable.AddScaleOp().Set(Gf.Vec3f(0.01, 0.01, 0.01))
                UsdGeom.Imageable(prim).MakeVisible()
            print(f"[baseline_diag] OBSTRUCTION applied — pallets moved to fallen positions", flush=True)

        else:
            _diag_resets += 1
            print(f"[baseline_diag] RESET triggered (reset #{_diag_resets})", flush=True)
            _reset_scene()

    for cmd in path_cmds:
        _, route_aisle, mission_kind = cmd
        _create_route_path(stage, route_aisle, mission_kind)

    now = time.monotonic()
    if _diag_update_tick % 600 == 0 or (now - _diag_last_report_ts > _DIAG_REPORT_INTERVAL and _diag_last_report_ts > 0):
        _diag_last_report_ts = now
        print(
            f"[baseline_diag] REPORT | tick={_diag_update_tick} | "
            f"qsize={_CMD_QUEUE.qsize()} drained_total={_diag_queue_drain_total} | "
            f"moves={_diag_moves_applied} obstructions={_diag_obstruction_cmds} resets={_diag_resets} | "
            f"telemetry: recv={_diag_telemetry_recv} enqueued={_diag_telemetry_enqueued} dropped={_diag_telemetry_dropped} | "
            f"alerts: recv={_diag_alert_recv} enqueued={_diag_alert_enqueued} | "
            f"lerp_t={_lerp_t:.2f} lerp_to={_lerp_to_pos}",
            flush=True,
        )


# ---------------------------------------------------------------------------
# Scene reset (startup + on-demand via reset command)
# ---------------------------------------------------------------------------

def _capture_original_xforms() -> None:
    """Snapshot the authored transforms of all managed prims after scene load."""
    from pxr import UsdGeom

    stage = omni.usd.get_context().get_stage()
    if stage is None:
        return
    for prim_path in [FORKLIFT_PRIM] + OBSTRUCTION_PRIMS:
        prim = stage.GetPrimAtPath(prim_path)
        if prim and prim.IsValid():
            _original_xforms[prim_path] = UsdGeom.Xformable(prim).GetLocalTransformation()
    print(f"[warehouse_baseline] captured {len(_original_xforms)} original xforms", flush=True)


def _reset_scene() -> None:
    """Snap forklift and obstruction prims back to their original positions."""
    from pxr import UsdGeom

    global _forklift_translate_op, _forklift_rotate_op
    global _lerp_from_pos, _lerp_from_yaw, _lerp_to_pos, _lerp_to_yaw, _lerp_t
    _forklift_translate_op = None
    _forklift_rotate_op = None
    _lerp_from_pos = None
    _lerp_to_pos = None
    _lerp_t = 1.0

    stage = omni.usd.get_context().get_stage()
    if stage is None:
        print("[baseline_diag] _reset_scene: stage is None — cannot reset", flush=True)
        return

    _remove_route_path(stage)

    restored = 0
    for prim_path, mat in _original_xforms.items():
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            print(f"[baseline_diag] _reset_scene: prim missing/invalid: {prim_path}", flush=True)
            continue
        xformable = UsdGeom.Xformable(prim)
        xformable.ClearXformOpOrder()
        op = xformable.AddTransformOp()
        op.Set(mat)
        UsdGeom.Imageable(prim).MakeVisible()
        restored += 1

    drained = 0
    while not _CMD_QUEUE.empty():
        try:
            _CMD_QUEUE.get_nowait()
            drained += 1
        except queue.Empty:
            break

    print(
        f"[baseline_diag] _reset_scene complete: {restored}/{len(_original_xforms)} prims restored, "
        f"{drained} queued commands drained, lerp state cleared",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def _reset_camera_state() -> None:
    """Publish CameraCommand(empty) so fake-camera matches the clean scene."""
    try:
        from confluent_kafka import Producer
    except ImportError:
        print("[warehouse_baseline] confluent_kafka unavailable — skipping camera reset", flush=True)
        return
    conf = {"bootstrap.servers": KAFKA_BOOTSTRAP}
    if KAFKA_SECURITY_PROTOCOL != "PLAINTEXT":
        conf["security.protocol"] = KAFKA_SECURITY_PROTOCOL
        conf["ssl.endpoint.identification.algorithm"] = "none"
        conf["enable.ssl.certificate.verification"] = "false"
    p = Producer(conf)
    import json as _json
    cmd = _json.dumps({
        "command_id": uuid.uuid4().hex,
        "trace_id": uuid.uuid4().hex,
        "camera_id": "cam-aisle-3",
        "state": "empty",
    })
    p.produce("warehouse.cameras.commands", key="cam-aisle-3", value=cmd.encode())
    p.flush(timeout=5.0)
    print("[warehouse_baseline] camera reset to empty", flush=True)


async def _run() -> None:
    try:
        print("[warehouse_baseline] _run() starting", flush=True)
        _register_nucleus_auth()
        await _open_scene()
        print("[warehouse_baseline] scene opened successfully", flush=True)

        _capture_original_xforms()
        _reset_camera_state()

        threading.Thread(target=_telemetry_consumer, daemon=True, name="twin-telemetry").start()
        threading.Thread(target=_alerts_consumer, daemon=True, name="twin-alerts").start()
        threading.Thread(target=_missions_consumer, daemon=True, name="twin-missions").start()

        global _UPDATE_SUB
        _UPDATE_SUB = (
            omni.kit.app.get_app()
            .get_update_event_stream()
            .create_subscription_to_pop(_apply_updates, name="twin-update")
        )

        omni.timeline.get_timeline_interface().play()
        print("[warehouse_baseline] timeline playing, twin subscribers active", flush=True)
    except Exception:
        print(f"[warehouse_baseline] _run() FAILED: {traceback.format_exc()}", flush=True)
        carb.log_error("warehouse_baseline: " + traceback.format_exc())


print("[warehouse_baseline] module loaded, scheduling _run()", flush=True)
omni.kit.app.get_app().get_post_update_event_stream()
asyncio.ensure_future(_run())


# ---------------------------------------------------------------------------
# Chain MJPEG viewport broadcaster
# ---------------------------------------------------------------------------

import sys as _sys  # noqa: E402
_sys.path.insert(0, "/scenarios")
import viewport_mjpeg  # noqa: E402,F401
import cosmos_capture  # noqa: E402,F401


# ---------------------------------------------------------------------------
# Static camera position (demo viewpoint)
# ---------------------------------------------------------------------------

def _install_camera_setup() -> None:
    try:
        from pxr import Gf, UsdGeom
    except Exception:
        return

    camera_path = "/OmniverseKit_Persp"
    cam_pos = Gf.Vec3d(-12.766, -6.168, 6.569)
    cam_axis = Gf.Vec3d(0.998, 0.0387, 0.0504)
    cam_angle = 75.14
    _applied = [False]

    def _tick(_event) -> None:
        if _applied[0]:
            return
        try:
            stage = omni.usd.get_context().get_stage()
            if stage is None:
                return
            if not stage.GetPrimAtPath(FORKLIFT_PRIM).IsValid():
                return
            cam = stage.GetPrimAtPath(camera_path)
            if not cam or not cam.IsValid():
                return
            rot = Gf.Rotation(cam_axis, cam_angle)
            mat = Gf.Matrix4d()
            mat.SetRotate(rot)
            mat.SetTranslateOnly(cam_pos)
            xformable = UsdGeom.Xformable(cam)
            xformable.ClearXformOpOrder()
            op = xformable.AddTransformOp()
            op.Set(mat)
            _applied[0] = True
            print(f"[camera_setup] set camera to pos={cam_pos}", flush=True)
        except Exception as e:
            print(f"[camera_setup] error: {e}", flush=True)

    global _CAMERA_SUB
    _CAMERA_SUB = (
        omni.kit.app.get_app()
        .get_update_event_stream()
        .create_subscription_to_pop(_tick, name="camera_setup")
    )


_install_camera_setup()


