import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { sceneToWorld, worldBoxToScene, worldToScene } from './axes.ts'
import { buildSceneModel, cameraFor, ruleTargetIds } from './scene.ts'
import { floorsShowing, moveBox, updatePort } from '../editor/model.ts'

const fixture = (name) => new URL(`../../../src/plan_route/fixtures/${name}`, import.meta.url)
const load = (name) => JSON.parse(readFileSync(fileURLToPath(fixture(name)), 'utf8'))
const demo = () => load('demo_project.json')

function cross(a, b) {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]].map((value) => value + 0)
}

function report(project, points, violations = []) {
  return {
    status: violations.length ? 'INVALID_ROUTE' : 'SUCCESS',
    project_id: project.project_id,
    pipe_id: project.pipes[0].id,
    algorithm: 'test',
    grid_resolution_m: project.routing_config.grid_resolution_m,
    points_m: points,
    bend_count: null,
    cost_breakdown: null,
    expanded_states: 0,
    runtime_ms: 0,
    applied_rule_ids: [],
    scenario_hash: 'x',
    validation: { status: violations.length ? 'FAIL' : 'PASS', violations },
  }
}

test('world z-up maps to scene y-up as a proper rotation and round-trips', () => {
  const ex = worldToScene([1, 0, 0])
  const ey = worldToScene([0, 1, 0])
  const ez = worldToScene([0, 0, 1])
  assert.deepEqual(ez, [0, 1, 0], 'world up is scene up')
  // x × y = z must survive the mapping, otherwise the scene would be mirrored.
  assert.deepEqual(cross(ex, ey), ez)
  for (const point of [[0, 0, 0], [12.5, -3.25, 7], [-4, 9, -1.5]]) {
    assert.deepEqual(sceneToWorld(worldToScene(point)), point)
  }
  assert.deepEqual(
    worldBoxToScene({ type: 'aabb', min_m: [2, 4, 1], max_m: [6, 5, 4] }),
    { center: [4, 2.5, -4.5], size: [4, 3, 1] },
  )
})

test('every obstacle, zone and port gets a scene object with the same id and position', () => {
  const project = load('plant_starter_project.json')
  const model = buildSceneModel(project, null, project.pipes[0].id)
  for (const obstacle of project.obstacles) {
    const box = model.boxes.find((item) => item.selection.kind === 'obstacle' && item.selection.id === obstacle.id)
    assert.ok(box, obstacle.id)
    assert.deepEqual(box.center, worldBoxToScene(obstacle.shape).center)
    assert.equal(box.style, obstacle.kind === 'slab' ? 'slab' : 'obstacle')
  }
  for (const zone of project.zones) {
    assert.ok(model.boxes.some((item) => item.selection.kind === 'zone' && item.selection.id === zone.id), zone.id)
  }
  const ports = project.equipment.flatMap((item) => item.ports)
  assert.equal(model.ports.length, ports.length)
  for (const port of ports) {
    assert.deepEqual(sceneToWorld(model.ports.find((item) => item.id === port.id).center), port.position_m)
  }
  assert.equal(model.route, null)
})

test('moving a wall in the 2D model moves its 3D box by the same metres', () => {
  const project = demo()
  const before = buildSceneModel(project, null, 'PIPE-101').boxes.find((item) => item.selection.id === 'WALL-01')
  // Plan drag reports the top-left corner: min x = 3, max y = 8 (metres); z extent stays as stored.
  const moved = moveBox(project, 'obstacle', 'WALL-01', 3, 8, 0.5)
  const after = buildSceneModel(moved, null, 'PIPE-101').boxes.find((item) => item.selection.id === 'WALL-01')
  assert.deepEqual(moved.obstacles[0].shape.min_m, [3, 1, 0])
  assert.deepEqual(sceneToWorld(after.center), [3.25, 4.5, 2])
  assert.deepEqual(after.size, before.size)
  assert.deepEqual(sceneToWorld(before.center), [5.25, 3.5, 2])
})

test('a moved port moves its 3D marker; orientation stub points along the port axis', () => {
  const project = updatePort(demo(), 'PORT-B', [10, 3, 1.5], '+z')
  const port = buildSceneModel(project, null, 'PIPE-101').ports.find((item) => item.id === 'PORT-B')
  assert.deepEqual(sceneToWorld(port.center), [10, 3, 1.5])
  const tip = sceneToWorld(port.tip)
  assert.equal(tip[0], 10)
  assert.equal(tip[1], 3)
  assert.ok(tip[2] > 1.5)
})

test('route tube segments sit exactly on the reported route points', () => {
  const project = demo()
  const points = [[1, 2, 1], [3, 2, 1], [3, 2, 3], [3, 9, 3], [11, 9, 3], [11, 2, 1]]
  const model = buildSceneModel(project, report(project, points), 'PIPE-101')
  assert.equal(model.route.points.length, points.length)
  model.route.points.forEach((point, index) => assert.deepEqual(sceneToWorld(point), points[index]))
  for (const segment of model.route.segments) {
    const from = points[segment.index]
    const to = points[segment.index + 1]
    const mid = sceneToWorld(segment.center)
    for (let axis = 0; axis < 3; axis++) assert.ok(Math.abs(mid[axis] - (from[axis] + to[axis]) / 2) < 1e-12)
    assert.ok(Math.abs(segment.length - Math.hypot(to[0] - from[0], to[1] - from[1], to[2] - from[2])) < 1e-12)
    // Cylinder end caps (centre ± direction·length/2) land on the route points.
    const end = sceneToWorld(segment.center.map((value, axis) => value + segment.direction[axis] * segment.length / 2))
    for (let axis = 0; axis < 3; axis++) assert.ok(Math.abs(end[axis] - to[axis]) < 1e-12)
  }
  // Insulated outer radius: 0.1 / 2 + 0.02.
  assert.ok(Math.abs(model.route.radius - 0.07) < 1e-12)
})

test('violated segments are flagged and a route for another pipe is not drawn', () => {
  const project = demo()
  const violation = { code: 'KEEP_OUT', segment_index: 1, object_id: 'ZONE-A', rule_id: 'RULE-001', measured_distance_m: 0, required_distance_m: 0, message: '' }
  const route = report(project, [[1, 2, 1], [5, 2, 1], [5, 6, 1], [11, 6, 1]], [violation])
  const model = buildSceneModel(project, route, 'PIPE-101')
  assert.deepEqual(model.route.segments.filter((item) => item.invalid).map((item) => item.index), [1])
  assert.equal(buildSceneModel(project, route, 'OTHER-PIPE').route, null)
  assert.equal(buildSceneModel(project, report(project, [[1, 2, 1]]), 'PIPE-101').route, null)
})

test('zone style follows rule approval and rule focus returns the targets', () => {
  const project = demo()
  const zone = (p) => buildSceneModel(p, null, 'PIPE-101').boxes.find((item) => item.selection.id === 'ZONE-A').style
  assert.equal(zone(project), 'keep-out')
  project.constraints[0].status = 'draft'
  assert.equal(zone(project), 'pending-zone')
  assert.deepEqual([...ruleTargetIds(project, 'RULE-001')], ['ZONE-A'])
  assert.equal(ruleTargetIds(project, 'NO-SUCH-RULE').size, 0)
  assert.equal(ruleTargetIds(project, null).size, 0)
})

test('camera presets look at the building centre; plan view looks straight down', () => {
  const bounds = { type: 'aabb', min_m: [0, 0, 0], max_m: [60, 40, 12] }
  const plan = cameraFor(bounds, 'plan')
  assert.deepEqual(sceneToWorld(plan.target), [30, 20, 6])
  const eye = sceneToWorld(plan.position)
  assert.ok(eye[2] > 12)
  assert.ok(Math.abs(eye[0] - 30) < 1e-9 && Math.abs(eye[1] - 20) < 0.1)
  const aerial = sceneToWorld(cameraFor(bounds, 'aerial').position)
  assert.ok(aerial[2] > 12 && aerial[0] < 30 && aerial[1] < 20)
})

test('a 3D selection resolves to the floors that draw it in 2D', () => {
  const project = load('plant_starter_project.json')
  const [lower, upper] = project.building.floors
  const port = project.equipment.flatMap((item) => item.ports).find((item) => item.position_m[2] < lower.z_max_m)
  assert.ok(floorsShowing(project, { kind: 'port', id: port.id }).includes(lower.id))
  const high = project.obstacles.find((item) => item.kind !== 'slab' && item.shape.min_m[2] >= upper.z_min_m)
  if (high) assert.deepEqual(floorsShowing(project, { kind: 'obstacle', id: high.id }), [upper.id])
  assert.deepEqual(floorsShowing(project, { kind: 'zone', id: 'NO-SUCH-ZONE' }), [])
})

test('selected pipe ports carry start/end roles and waypoints keep sequence order and position', () => {
  const project = demo()
  project.pipes[0].waypoints = [
    { id: 'WP-B', position_m: [8.25, 9.25, 2.25] },
    { id: 'WP-A', position_m: [2.25, 9.25, 2.25], pass_axis: 'y' },
  ]
  const model = buildSceneModel(project, null, 'PIPE-101')
  assert.deepEqual(model.ports.map((port) => [port.id, port.role]), [['PORT-A', 'start'], ['PORT-B', 'end']])
  assert.deepEqual(model.waypoints.map((item) => [item.id, item.order]), [['WP-B', 1], ['WP-A', 2]])
  assert.deepEqual(sceneToWorld(model.waypoints[0].center), [8.25, 9.25, 2.25])
  assert.equal(model.waypoints[0].axis, null)
  const [from, to] = model.waypoints[1].axis.map(sceneToWorld)
  assert.equal(from[0], 2.25)
  assert.equal(from[2], 2.25)
  assert.ok(from[1] < 9.25 && to[1] > 9.25, 'guide runs along world y')
  const other = buildSceneModel(project, null, 'NO-SUCH-PIPE')
  assert.deepEqual(other.waypoints, [])
  assert.ok(other.ports.every((port) => port.role === null))
})
