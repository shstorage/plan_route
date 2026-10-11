import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import {
  fitView, planToWorld, screenToWorld, snapMeters, worldBoxToPlan,
  worldToPlan, worldToScreen, zoomAt,
} from './coordinates.ts'
import {
  connectPort, createBox, createPort, createRule, defaultPortHeight, deleteObject, drawBox,
  gridCellCount, metresToMillimetres, millimetresToMetres, moveBox, pipeEnvelopeDiameter,
  resizeBox, routeSegmentsOnFloor, updateDomain, updatePipe, updatePort, updateRule,
} from './model.ts'
import { pushHistory, redoHistory, startHistory, undoHistory } from './history.ts'

const fixture = new URL('../../../src/plan_route/fixtures/demo_project.json', import.meta.url)
// The fixture lives at the repository root, outside frontend/src/editor.
const project = () => JSON.parse(readFileSync(fileURLToPath(fixture), 'utf8'))

test('world metres and screen pixels round-trip with offset, zoom and inverted y', () => {
  const bounds = { type: 'aabb', min_m: [-4, -2, 0], max_m: [8, 10, 4] }
  const view = fitView(bounds, 800, 600)
  const point = [1.25, 3.75, 2]
  const screen = worldToScreen(point, bounds, view)
  const restored = screenToWorld(screen, 2, bounds, view)
  assert.deepEqual(restored, point)
  assert.deepEqual(worldToPlan(point, bounds), { x: 5.25, y: 6.25 })
  assert.deepEqual(planToWorld({ x: 5.25, y: 6.25 }, 2, bounds), point)
  assert.deepEqual(worldBoxToPlan({ type: 'aabb', min_m: [0, 1, 0], max_m: [2, 4, 4] }, bounds), {
    x: 4, y: 6, width: 2, height: 3,
  })
  const zoomed = zoomAt(view, screen, 1.5, 10, 200)
  assert.deepEqual(worldToScreen(point, bounds, zoomed), screen)
})

test('snapping respects coordinate origin and rejects bad step', () => {
  assert.equal(snapMeters(2.24, 0.5, 0.1), 2.1)
  assert.equal(snapMeters(2.4, 0.5, 0.1), 2.6)
  assert.throws(() => snapMeters(1, 0), /스냅/)
})

test('moving and resizing a wall changes only domain metres and rejects invalid geometry', () => {
  const original = project()
  const moved = moveBox(original, 'obstacle', 'WALL-01', 6.1, 9, 0.5)
  assert.deepEqual(original.obstacles[0].shape.min_m, [5, 0, 0])
  assert.deepEqual(moved.obstacles[0].shape.min_m, [6, 2, 0])
  assert.deepEqual(moved.obstacles[0].shape.max_m, [6.5, 9, 4])
  const resized = resizeBox(moved, 'obstacle', 'WALL-01', 'se', 7.1, 1.4, 0.5)
  assert.deepEqual(resized.obstacles[0].shape.min_m, [6, 1.5, 0])
  assert.deepEqual(resized.obstacles[0].shape.max_m, [7, 9, 4])
  assert.throws(() => resizeBox(original, 'obstacle', 'WALL-01', 'ne', 4, 8, 0.5), /최소/)
  assert.throws(() => moveBox(original, 'obstacle', 'WALL-01', 20, 9, 0.5), /경계/)
})

test('creating Zone and Port keeps unique IDs and metre coordinates', () => {
  const original = project()
  const floor = original.building.floors[0]
  const addedZone = createBox(original, 'zone', [2.1, 5.7, 2], floor, 0.5)
  assert.equal(addedZone.selection.id, 'ZONE-001')
  assert.deepEqual(addedZone.project.zones[1].shape.min_m, [2, 5, 0])
  assert.deepEqual(addedZone.project.zones[1].shape.max_m, [2.5, 5.5, 4])
  const addedPort = createPort(addedZone.project, 'PUMP-101', [2.1, 5.7, 1], floor, 0.5)
  assert.equal(addedPort.selection.id, 'PORT-001')
  // New ports reuse the height of PORT-A (1 m) on the same floor.
  assert.deepEqual(addedPort.project.equipment[0].ports[1].position_m, [2, 5.5, 1])
  const connected = connectPort(addedPort.project, 'PIPE-101', 'from', addedPort.selection.id)
  assert.equal(connected.pipes[0].from_port_id, 'PORT-001')
  assert.equal(original.pipes[0].from_port_id, 'PORT-A')
  assert.throws(() => connectPort(original, 'PIPE-101', 'from', 'PORT-B'), /서로 다른/)
  assert.throws(() => createPort(original, 'MISSING', [2, 2, 1], floor, 0.5), /소유 장비/)
  assert.throws(() => updatePort(original, 'PORT-A', [99, 2, 1]), /건물 내부/)
})

test('rule editing requires an explicit distance and valid target', () => {
  const original = project()
  assert.throws(() => updateRule(original, 'RULE-001', {
    type: 'MIN_CLEARANCE', status: 'draft', targetId: 'WALL-01', distanceText: '',
  }), /거리/)
  const changed = updateRule(original, 'RULE-001', {
    type: 'MIN_CLEARANCE', status: 'needs_review', targetId: 'WALL-01', distanceText: '0.3',
  })
  assert.equal(changed.constraints[0].parameters.distance_m, 0.3)
  assert.equal(changed.constraints[0].status, 'needs_review')
  assert.equal(original.constraints[0].status, 'approved')
  assert.throws(() => updateRule(original, 'RULE-001', {
    type: 'KEEP_OUT', status: 'approved', targetId: 'WALL-01', distanceText: '',
  }), /대상/)
})

test('new rules require real provenance and remain draft until explicitly approved', () => {
  const original = project()
  const input = {
    pipeId: 'PIPE-101', targetId: 'ZONE-A', type: 'KEEP_OUT', distanceText: '',
    documentId: 'STUDY-01', revision: '1', clauseId: 'A-1', evidence: 'Synthetic exclusion',
  }
  assert.throws(() => createRule(original, { ...input, evidence: '' }), /근거/)
  assert.throws(() => createRule(original, { ...input, documentId: '../bad' }), /문서 ID/)
  const added = createRule(original, input)
  assert.equal(added.id, 'RULE-002')
  assert.equal(added.project.constraints[1].status, 'draft')
  assert.equal(added.project.constraints[1].source.document_id, 'STUDY-01')
})

test('route projection clips a vertical segment to the selected floor', () => {
  const floor = { id: 'L2', z_min_m: 2, z_max_m: 4 }
  const segments = routeSegmentsOnFloor([[1, 1, 1], [1, 1, 5], [3, 1, 5]], floor)
  assert.equal(segments.length, 1)
  assert.deepEqual(segments[0].from, [1, 1, 2])
  assert.deepEqual(segments[0].to, [1, 1, 4])
})

test('undo/redo walks domain JSON snapshots and a new edit clears redo', () => {
  const original = project()
  const first = JSON.stringify(original)
  const second = JSON.stringify(moveBox(original, 'obstacle', 'WALL-01', 6, 9, 0.5))
  const third = JSON.stringify(moveBox(original, 'obstacle', 'WALL-01', 3, 9, 0.5))
  let history = pushHistory(startHistory(first), second)
  assert.equal(pushHistory(history, second), history)
  history = undoHistory(history)
  assert.equal(history.present, first)
  assert.equal(undoHistory(history), history)
  history = redoHistory(history)
  assert.equal(history.present, second)
  assert.equal(redoHistory(history), history)
  history = pushHistory(undoHistory(history), third)
  assert.equal(history.present, third)
  assert.deepEqual(history.future, [])
  assert.deepEqual(history.past, [first])
  let capped = startHistory('0')
  for (let index = 1; index <= 5; index++) capped = pushHistory(capped, String(index), 3)
  assert.deepEqual(capped.past, ['2', '3', '4'])
})

test('drawing a box snaps both corners in any drag direction and falls back to a default square on click', () => {
  const original = project()
  const floor = original.building.floors[0]
  const drawn = drawBox(original, 'obstacle', [8.9, 1.1, 2], [7.1, 6.2, 2], floor, 0.5)
  assert.equal(drawn.selection.id, 'WALL-001')
  assert.deepEqual(drawn.project.obstacles[1].shape, { type: 'aabb', min_m: [7, 1, 0], max_m: [9, 6, 4] })
  const clicked = drawBox(original, 'zone', [2.1, 5.7, 2], [2.15, 5.72, 2], floor, 0.5)
  assert.deepEqual(clicked.project.zones[1].shape, { type: 'aabb', min_m: [2, 5, 0], max_m: [2.5, 5.5, 4] })
  // Drawing over an existing zone is allowed; drawing outside the building is not.
  assert.equal(drawBox(original, 'obstacle', [4.5, 4.5, 2], [6, 6, 2], floor, 0.5).project.obstacles.length, 2)
  assert.throws(() => drawBox(original, 'obstacle', [10, 8, 2], [14, 9, 2], floor, 0.5), /경계/)
})

test('deleting objects is blocked while a rule, pipe or equipment still needs them', () => {
  const original = project()
  assert.throws(() => deleteObject(original, { kind: 'zone', id: 'ZONE-A' }), /RULE-001/)
  assert.throws(() => deleteObject(original, { kind: 'port', id: 'PORT-A' }), /PIPE-101/)
  const removed = deleteObject(original, { kind: 'obstacle', id: 'WALL-01' })
  assert.equal(removed.obstacles.length, 0)
  assert.equal(original.obstacles.length, 1)
  const floor = original.building.floors[0]
  const withPort = createPort(original, 'PUMP-101', [3, 3, 1], floor, 0.5)
  const portRemoved = deleteObject(withPort.project, withPort.selection)
  assert.deepEqual(portRemoved.equipment, original.equipment)
  const lonely = { ...original, pipes: [], constraints: [] }
  const onlyPortOwner = lonely.equipment.find((item) => item.ports.length === 1)
  assert.throws(() => deleteObject(lonely, { kind: 'port', id: onlyPortOwner.ports[0].id }), /마지막 Port/)
  assert.throws(() => deleteObject(original, { kind: 'obstacle', id: 'MISSING' }), /찾을 수 없/)
})

test('domain bounds, floors and grid can change, but cannot shrink past objects or explode the grid', () => {
  const original = project()
  const edit = {
    minText: ['0', '0', '0'], maxText: ['20', '15', '6'],
    floors: [{ id: 'L1', zMinText: '0', zMaxText: '6' }], gridText: '0.25',
  }
  const grown = updateDomain(original, edit)
  assert.deepEqual(grown.building.bounds_m.max_m, [20, 15, 6])
  assert.equal(grown.building.floors[0].z_max_m, 6)
  assert.equal(grown.routing_config.grid_resolution_m, 0.25)
  assert.equal(grown.routing_config.search_limits.max_expansions, original.routing_config.search_limits.max_expansions)
  assert.throws(() => updateDomain(original, {
    ...edit, maxText: ['10', '10', '4'], floors: [{ id: 'L1', zMinText: '0', zMaxText: '4' }],
  }), /PORT-B/)
  assert.throws(() => updateDomain(original, { ...edit, maxText: ['20', '15', ''] }), /Z 최대/)
  assert.throws(() => updateDomain(original, { ...edit, floors: [{ id: 'L1', zMinText: '0', zMaxText: '7' }] }), /범위/)
  assert.throws(() => updateDomain(original, { ...edit, floors: [{ id: 'L1', zMinText: '3', zMaxText: '3' }] }), /낮아야/)
  assert.throws(() => updateDomain(original, { ...edit, floors: [] }), /층 목록/)
  assert.throws(() => updateDomain(original, { ...edit, gridText: '0' }), /0.05/)
  assert.throws(() => updateDomain(original, { ...edit, gridText: 'abc' }), /격자 간격/)
  // 500 x 500 x 12 m at 0.1 m would be 300 million cells.
  assert.throws(() => updateDomain(original, {
    ...edit, maxText: ['500', '500', '12'], floors: [{ id: 'L1', zMinText: '0', zMaxText: '12' }], gridText: '0.1',
  }), /너무 많/)
})

test('grid cell count matches backend rounding, including a clipped final cell', () => {
  assert.equal(gridCellCount([0, 0, 0], [60, 40, 12], 0.5), 120 * 80 * 24)
  assert.equal(gridCellCount([0, 0, 0], [12, 10, 4], 0.5), 24 * 20 * 8)
  assert.equal(gridCellCount([0, 0, 0], [2.3, 1, 1], 1), 3)
  assert.equal(gridCellCount([0, 0, 0], [0.3, 0.3, 0.3], 0.1), 27)
})

test('pipe section edits are entered in mm, stored in metres and validated', () => {
  const original = project()
  assert.equal(millimetresToMetres('114.3'), '0.1143')
  assert.equal(millimetresToMetres('abc'), 'abc')
  assert.equal(metresToMillimetres(0.1143), 114.3)
  const changed = updatePipe(original, 'PIPE-101', { outerDiameterText: '0.1143', insulationText: '0.04', marginText: '0.05' })
  const pipe = changed.pipes[0]
  assert.deepEqual([pipe.outer_diameter_m, pipe.insulation_thickness_m, pipe.clearance_margin_m], [0.1143, 0.04, 0.05])
  assert.ok(Math.abs(pipeEnvelopeDiameter(pipe) - 0.2943) < 1e-12)
  assert.equal(pipeEnvelopeDiameter(original.pipes[0]), 0.14)
  assert.equal(original.pipes[0].clearance_margin_m, undefined)
  const edit = { outerDiameterText: '0.1', insulationText: '0', marginText: '0' }
  assert.throws(() => updatePipe(original, 'PIPE-101', { ...edit, outerDiameterText: '0' }), /외경/)
  assert.throws(() => updatePipe(original, 'PIPE-101', { ...edit, marginText: '-0.01' }), /0 이상/)
  assert.throws(() => updatePipe(original, 'PIPE-101', { ...edit, insulationText: 'abc' }), /보온재/)
  assert.throws(() => updatePipe(original, 'MISSING', edit), /MISSING/)
})

test('default port height reuses a port on the floor, else 1 m above the slab', () => {
  const original = project()
  assert.equal(defaultPortHeight(original, original.building.floors[0]), 1)
  assert.equal(defaultPortHeight(original, { id: 'L2', z_min_m: 4, z_max_m: 8 }), 5)
  assert.equal(defaultPortHeight(original, { id: 'L3', z_min_m: 4, z_max_m: 5 }), 4.5)
})
