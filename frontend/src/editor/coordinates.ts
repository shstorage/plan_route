import type { Aabb, Point3 } from '../api/client'

export type PlanPoint = { x: number; y: number }
export type PlanView = { scale: number; panX: number; panY: number }

export function worldToPlan(point: Point3, bounds: Aabb): PlanPoint {
  return { x: point[0] - bounds.min_m[0], y: bounds.max_m[1] - point[1] }
}

export function planToWorld(point: PlanPoint, z: number, bounds: Aabb): Point3 {
  return [bounds.min_m[0] + point.x, bounds.max_m[1] - point.y, z]
}

export function worldToScreen(point: Point3, bounds: Aabb, view: PlanView): PlanPoint {
  const plan = worldToPlan(point, bounds)
  return { x: plan.x * view.scale + view.panX, y: plan.y * view.scale + view.panY }
}

export function screenToWorld(point: PlanPoint, z: number, bounds: Aabb, view: PlanView): Point3 {
  if (!Number.isFinite(view.scale) || view.scale <= 0) throw new Error('화면 배율이 올바르지 않습니다.')
  return planToWorld({ x: (point.x - view.panX) / view.scale, y: (point.y - view.panY) / view.scale }, z, bounds)
}

export function worldBoxToPlan(box: Aabb, bounds: Aabb) {
  return {
    x: box.min_m[0] - bounds.min_m[0],
    y: bounds.max_m[1] - box.max_m[1],
    width: box.max_m[0] - box.min_m[0],
    height: box.max_m[1] - box.min_m[1],
  }
}

export function fitView(bounds: Aabb, width: number, height: number, padding = 36): PlanView {
  const spanX = bounds.max_m[0] - bounds.min_m[0]
  const spanY = bounds.max_m[1] - bounds.min_m[1]
  const scale = Math.min((width - 2 * padding) / spanX, (height - 2 * padding) / spanY)
  if (!Number.isFinite(scale) || scale <= 0) throw new Error('도면 크기가 올바르지 않습니다.')
  return {
    scale,
    panX: (width - spanX * scale) / 2,
    panY: (height - spanY * scale) / 2,
  }
}

export function zoomAt(view: PlanView, pointer: PlanPoint, factor: number, min: number, max: number): PlanView {
  const scale = Math.max(min, Math.min(max, view.scale * factor))
  const ratio = scale / view.scale
  return {
    scale,
    panX: pointer.x - (pointer.x - view.panX) * ratio,
    panY: pointer.y - (pointer.y - view.panY) * ratio,
  }
}

export function snapMeters(value: number, step: number, origin = 0): number {
  if (!Number.isFinite(value) || !Number.isFinite(step) || step <= 0) {
    throw new Error('스냅 간격 또는 좌표가 올바르지 않습니다.')
  }
  return Number((origin + Math.round((value - origin) / step) * step).toFixed(9))
}
