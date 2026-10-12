// Exercise the same domain functions used by the UI; no fixture or API dependency.
import { createBlankProject, createEquipment, deleteEquipment, deletePipe, moveBox, pickConnection, renameProject } from '../frontend/src/editor/model.ts'

const blank = createBlankProject('SYNTH-EDITOR-EMPTY')
const first = createEquipment(blank, 'pump', [5, 6, 0], blank.building.floors[0], 0.5)
const second = createEquipment(first.project, 'heat_exchanger', [15, 6, 0], blank.building.floors[0], 0.5)
const from = second.project.equipment[0].ports[1].id
const to = second.project.equipment[1].ports[0].id
const firstClick = pickConnection(second.project, null, from)
const connected = pickConnection(firstClick.project, firstClick.startPortId, to)
const built = connected.project
const body = built.obstacles.find((item) => item.id === built.equipment[1].geometry_ref)
const moved = moveBox(built, 'obstacle', body.id, body.shape.min_m[0] + 1, body.shape.max_m[1], null)
const removedPipe = deletePipe(moved, connected.pipeId)
const cleaned = deleteEquipment(deleteEquipment(removedPipe, first.equipmentId), second.equipmentId)
const named = renameProject(built, '배관 연구 프로젝트')
const near = createEquipment(first.project, 'pump', [8, 6, 0], blank.building.floors[0], 0.5)
const nearClick = pickConnection(near.project, null, near.project.equipment[0].ports[1].id)
const nearPipe = pickConnection(nearClick.project, nearClick.startPortId, near.project.equipment[1].ports[0].id)
const nearBody = nearPipe.project.obstacles.find((item) => item.id === nearPipe.project.equipment[1].geometry_ref)
const repaired = moveBox(nearPipe.project, 'obstacle', nearBody.id, 14, nearBody.shape.max_m[1], null)
process.stdout.write(JSON.stringify({ blank, built, moved, cleaned, named, blocked: nearPipe.project, repaired, pipeId: connected.pipeId }))
