import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import {
  fitView, planToWorld, screenToWorld, snapMeters, worldBoxToPlan,
  worldToPlan, worldToScreen, zoomAt,
} from './coordinates.ts'
import {
  connectPort, createBox, createPort, createRule, moveBox, resizeBox, routeSegmentsOnFloor,
  updatePort, updateRule,
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
  assert.deepEqual(addedPort.project.equipment[0].ports[1].position_m, [2, 5.5, 2])
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
