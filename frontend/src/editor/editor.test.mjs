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

test('rule editing covers several pipes and targets and requires a distance for clearance', () => {
  const original = project()
  const base = { type: 'MIN_CLEARANCE', status: 'draft', pipeIds: ['PIPE-101'], targetIds: ['WALL-01'], distanceText: '' }
  assert.throws(() => updateRule(original, 'RULE-001', base), /거리/)
  const changed = updateRule(original, 'RULE-001', { ...base, status: 'needs_review', targetIds: ['WALL-01', 'ZONE-A'], distanceText: '0.3' })
  assert.deepEqual(changed.constraints[0].scope, { pipe_ids: ['PIPE-101'], target_ids: ['WALL-01', 'ZONE-A'] })
  assert.equal(changed.constraints[0].parameters.distance_m, 0.3)
  assert.equal(changed.constraints[0].status, 'needs_review')
  assert.equal(original.constraints[0].status, 'approved')
  assert.throws(() => updateRule(original, 'RULE-001', { ...base, type: 'KEEP_OUT', targetIds: ['ZONE-A', 'WALL-01'] }), /Zone이어야/)
  assert.throws(() => updateRule(original, 'RULE-001', { ...base, targetIds: [], distanceText: '1' }), /대상을 하나 이상/)
  assert.throws(() => updateRule(original, 'RULE-001', { ...base, pipeIds: [], distanceText: '1' }), /배관을 하나 이상/)
  assert.throws(() => updateRule(original, 'RULE-001', { ...base, pipeIds: ['NOPE'], distanceText: '1' }), /존재하지 않는 배관/)
  assert.throws(() => updateRule(original, 'RULE-001', { ...base, targetIds: ['WALL-01', 'WALL-01'], distanceText: '1' }), /두 번/)
})

test('editing an approved definition clears approval and increments revision', () => {
  const original = project()
  const changed = updateRule(original, 'RULE-001', {
    type: 'MIN_CLEARANCE', status: 'approved', pipeIds: ['PIPE-101'],
    targetIds: ['WALL-01'], distanceText: '0.3',
  })
  const rule = changed.constraints[0]
  assert.equal(rule.status, 'needs_review')
  assert.equal(rule.definition_revision, 2)
  assert.equal(rule.approved_by, null)
  assert.equal(rule.approved_at, null)
  assert.equal(rule.approved_content_sha256, null)
  assert.equal(original.constraints[0].status, 'approved')
})

test('new rules require real provenance and remain draft until explicitly approved', () => {
  const original = project()
  const input = {
    pipeIds: ['PIPE-101'], targetIds: ['ZONE-A'], type: 'KEEP_OUT', distanceText: '',
    documentId: 'STUDY-01', revision: '1', clauseId: 'A-1', evidence: 'Synthetic exclusion',
  }
  assert.throws(() => createRule(original, { ...input, evidence: '' }), /근거/)
  assert.throws(() => createRule(original, { ...input, documentId: '../bad' }), /문서 ID/)
  const added = createRule(original, input)
  assert.equal(added.id, 'RULE-002')
  assert.equal(added.project.constraints[1].status, 'draft')
  assert.equal(added.project.constraints[1].source.document_id, 'STUDY-01')
  const two = createRule(added.project, { ...input, type: 'MIN_CLEARANCE', targetIds: ['WALL-01', 'ZONE-A'], distanceText: '0.5' })
  assert.equal(two.id, 'RULE-003')
  assert.deepEqual(two.project.constraints[2].scope.target_ids, ['WALL-01', 'ZONE-A'])
  assert.equal(two.project.constraints.length, 3, 'rules accumulate; none replaces another')
})

test('rules read as sentences, report their effect per pipe, and can be deleted', async () => {
  const { deleteRule, describeRule, ruleEffect, ruleTargetOptions } = await import('./model.ts')
  const original = project()
  const rule = original.constraints[0]
  assert.equal(describeRule(rule), 'PIPE-101 배관은 ZONE-A 안으로 들어갈 수 없습니다.')
  assert.equal(describeRule({ ...rule, type: 'MIN_CLEARANCE', parameters: { distance_m: 0.5 }, scope: { pipe_ids: ['P1', 'P2'], target_ids: ['W1', 'Z1'] } }),
    'P1, P2 배관 외곽은 W1, Z1 표면에서 0.5 m 이상 떨어져야 합니다.')
  assert.equal(ruleEffect(rule, 'PIPE-101'), 'applied')
  assert.equal(ruleEffect({ ...rule, status: 'draft' }, 'PIPE-101'), 'blocking')
  assert.equal(ruleEffect({ ...rule, status: 'rejected' }, 'PIPE-101'), 'blocking')
  assert.equal(ruleEffect(rule, 'PIPE-999'), 'other-pipe')
  assert.deepEqual(ruleTargetOptions(original, 'KEEP_OUT'), ['ZONE-A'])
  assert.deepEqual(ruleTargetOptions(original, 'MIN_CLEARANCE'), ['ZONE-A', 'WALL-01'])
  assert.equal(deleteRule(original, 'RULE-001').constraints.length, 0)
  assert.throws(() => deleteRule(original, 'RULE-404'), /RULE-404/)
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

test('waypoints: add in sequence, snap to cell centres, reorder, edit and remove', async () => {
  const { addWaypoint, findWaypoint, portRole, removeWaypoint, reorderWaypoint, snapToCellCentre, updateWaypoint, floorsShowing } = await import('./model.ts')
  const base = project()
  const floor = base.building.floors[0]
  assert.equal(portRole(base, 'PIPE-101', 'PORT-A'), 'start')
  assert.equal(portRole(base, 'PIPE-101', 'PORT-B'), 'end')
  assert.equal(portRole(base, 'NO-PIPE', 'PORT-A'), null)
  // Demo grid 0.5 m from x=0: cell centres at 0.25, 0.75, ...
  assert.deepEqual(snapToCellCentre(base, [2.1, 3.4, 1.0]), [2.25, 3.25, 1.25])
  assert.deepEqual(snapToCellCentre(base, [-5, 99, 0]), [0.25, 9.75, 0.25])

  const first = addWaypoint(base, 'PIPE-101', [2.1, 3.4, 0], floor, true)
  assert.deepEqual(first.selection, { kind: 'waypoint', id: 'WP-001' })
  assert.deepEqual(first.project.pipes[0].waypoints, [{ id: 'WP-001', position_m: [2.25, 3.25, 1.25] }])
  assert.equal(base.pipes[0].waypoints, undefined, 'input project is not mutated')
  const second = addWaypoint(first.project, 'PIPE-101', [8, 9, 0], floor, true)
  assert.deepEqual(second.project.pipes[0].waypoints.map((item) => item.id), ['WP-001', 'WP-002'])
  assert.equal(second.project.pipes[0].waypoints[1].position_m[2], 1.25, 'reuses the floor height of earlier waypoints')
  assert.deepEqual(floorsShowing(second.project, second.selection), ['L1'])
  assert.throws(() => addWaypoint(base, 'NO-PIPE', [1, 1, 1], floor, true), /배관/)

  const swapped = reorderWaypoint(second.project, 'WP-002', -1)
  assert.deepEqual(swapped.pipes[0].waypoints.map((item) => item.id), ['WP-002', 'WP-001'])
  assert.equal(reorderWaypoint(swapped, 'WP-002', -1), swapped, 'first stays first')
  assert.equal(findWaypoint(swapped, 'WP-001').index, 1)

  const edited = updateWaypoint(swapped, 'WP-001', { position: [4.25, 9.25, 2.25], passAxis: 'x', note: '  C-101 sleeve  ' })
  assert.deepEqual(findWaypoint(edited, 'WP-001').waypoint, { id: 'WP-001', position_m: [4.25, 9.25, 2.25], pass_axis: 'x', note: 'C-101 sleeve' })
  const cleared = updateWaypoint(edited, 'WP-001', { passAxis: null, note: '' })
  assert.deepEqual(findWaypoint(cleared, 'WP-001').waypoint, { id: 'WP-001', position_m: [4.25, 9.25, 2.25] })
  assert.throws(() => updateWaypoint(edited, 'WP-001', { position: [99, 1, 1] }), /건물 내부/)
  assert.throws(() => updateWaypoint(edited, 'WP-404', {}), /WP-404/)

  const one = removeWaypoint(edited, 'WP-002')
  assert.deepEqual(one.pipes[0].waypoints.map((item) => item.id), ['WP-001'])
  const none = deleteObject(one, { kind: 'waypoint', id: 'WP-001' })
  assert.equal('waypoints' in none.pipes[0], false, 'empty sequence serialises like the original pipe')
  assert.deepEqual(none, base)
})

test('route floor crossings mark where the route continues to the next storey', async () => {
  const { routeFloorCrossings } = await import('./model.ts')
  const floors = [{ id: 'L1', z_min_m: 0, z_max_m: 6 }, { id: 'L2', z_min_m: 6, z_max_m: 12 }]
  const points = [[1, 1, 1], [4, 1, 1], [4, 1, 8], [9, 2, 8], [9, 2, 3], [10, 2, 3]]
  assert.deepEqual(routeFloorCrossings(points, floors[0], floors), [
    { at: [4, 1, 6], direction: 'up', floorId: 'L2' },
    { at: [9, 2, 6], direction: 'up', floorId: 'L2' },
  ])
  assert.deepEqual(routeFloorCrossings(points, floors[1], floors), [
    { at: [4, 1, 6], direction: 'down', floorId: 'L1' },
    { at: [9, 2, 6], direction: 'down', floorId: 'L1' },
  ])
  assert.deepEqual(routeFloorCrossings([[1, 1, 1], [5, 1, 1], [5, 1, 4]], floors[0], floors), [], 'stays on L1')
  assert.deepEqual(routeFloorCrossings([[1, 1, 5], [1, 1, 6]], floors[0], floors), [], 'touching the ceiling is not leaving')
})

test('new-rule form lists every required field still missing', async () => {
  const { missingForNewRule } = await import('./model.ts')
  const empty = { pipeIds: ['PIPE-101'], targetIds: [], type: 'MIN_CLEARANCE', distanceText: '', documentId: '', revision: '', clauseId: '', evidence: '' }
  assert.deepEqual(missingForNewRule(empty), ['대상', '최소 거리', '문서 ID', '개정판', '조항 ID', '근거 문구'])
  assert.deepEqual(missingForNewRule({ ...empty, type: 'KEEP_OUT', pipeIds: [] }), ['적용 배관', '대상', '문서 ID', '개정판', '조항 ID', '근거 문구'])
  assert.deepEqual(missingForNewRule({ ...empty, targetIds: ['WALL-01'], distanceText: '1', documentId: 'S', revision: '1', clauseId: 'A', evidence: 'x' }), [])
})

test('default rule source fills study-assumption provenance with the next free clause', async () => {
  const { createRule, defaultRuleSource, missingForNewRule } = await import('./model.ts')
  const base = project()
  const scope = { type: 'MIN_CLEARANCE', pipeIds: ['PIPE-101'], targetIds: ['WALL-01'], distanceText: '0.5' }
  const first = defaultRuleSource(base, scope)
  assert.deepEqual(first, {
    documentId: 'SYNTH-ASSUMPTION', revision: '1', clauseId: 'A-1',
    evidence: '연구용 가정(실제 법규·설계기준 값 아님): PIPE-101 배관 외곽은 WALL-01 표면에서 0.5 m 이상 떨어진다.',
  })
  const created = createRule(base, { ...scope, ...first })
  const rule = created.project.constraints.at(-1)
  assert.equal(rule.status, 'draft', 'still a draft that needs explicit approval')
  assert.equal(rule.source.source_type, 'synthetic_assumption')
  assert.equal(defaultRuleSource(created.project, scope).clauseId, 'A-2', 'clause numbers do not repeat')
  assert.match(defaultRuleSource(base, { type: 'KEEP_OUT', pipeIds: ['PIPE-101'], targetIds: ['ZONE-A'], distanceText: '' }).evidence, /ZONE-A 안으로 들어가지 않는다/)
  // Defaults never fill the rule itself: scope and distance stay required.
  assert.deepEqual(missingForNewRule({ ...scope, targetIds: [], distanceText: '', ...defaultRuleSource(base, scope) }), ['대상', '최소 거리'])
})
