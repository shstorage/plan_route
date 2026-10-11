import { useEffect, useMemo } from 'react'
import { useThree } from '@react-three/fiber'
import * as THREE from 'three'
import type { ScenePoint } from './axes.ts'

type Props = {
  position: ScenePoint
  text: string
  /** Text colour. */
  color: string
  /** Pill background; omit for plain text with a white halo. */
  background?: string
  /** Rounded square instead of a pill (waypoint numbers). */
  square?: boolean
  /** Label height on screen in CSS pixels, independent of camera distance. */
  heightPx?: number
  /** Screen offset of the label centre from the anchor point, in CSS pixels (+x right, +y up). */
  offsetPx?: [number, number]
}

const SUPERSAMPLE = 3

function drawLabel(text: string, color: string, background: string | undefined, square: boolean) {
  const fontPx = 13 * SUPERSAMPLE
  const pad = (background ? 6 : 3) * SUPERSAMPLE
  const height = 20 * SUPERSAMPLE
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d')!
  const font = `800 ${fontPx}px system-ui, -apple-system, 'Segoe UI', 'Malgun Gothic', sans-serif`
  context.font = font
  const width = Math.max(height, Math.ceil(context.measureText(text).width) + pad * 2)
  canvas.width = width
  canvas.height = height
  context.font = font
  context.textAlign = 'center'
  context.textBaseline = 'middle'
  if (background) {
    context.fillStyle = background
    context.beginPath()
    context.roundRect(0, 0, width, height, square ? 4 * SUPERSAMPLE : height / 2)
    context.fill()
  } else {
    context.lineWidth = 4 * SUPERSAMPLE
    context.strokeStyle = '#ffffff'
    context.lineJoin = 'round'
    context.strokeText(text, width / 2, height / 2 + SUPERSAMPLE)
  }
  context.fillStyle = color
  context.fillText(text, width / 2, height / 2 + SUPERSAMPLE)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 4
  return { texture, aspect: width / height }
}

/**
 * Text drawn into the WebGL scene as a camera-facing sprite with a constant screen size.
 * Labels stay in the canvas (no DOM overlay), are always drawn on top, and never take clicks.
 */
export function TextLabel({ position, text, color, background, square = false, heightPx = 20, offsetPx = [0, 0] }: Props) {
  const fov = useThree((state) => ('fov' in state.camera ? (state.camera as THREE.PerspectiveCamera).fov : 45))
  const viewportHeight = useThree((state) => state.size.height)
  const { texture, aspect } = useMemo(() => drawLabel(text, color, background, square), [text, color, background, square])
  useEffect(() => () => texture.dispose(), [texture])
  // With sizeAttenuation off, a sprite of scale s spans s / (2 tan(fov / 2)) of the viewport height.
  const unit = (2 * Math.tan((fov * Math.PI) / 360)) / Math.max(1, viewportHeight)
  const height = heightPx * unit
  const widthPx = heightPx * aspect
  const center: [number, number] = [0.5 - offsetPx[0] / widthPx, 0.5 - offsetPx[1] / heightPx]
  return (
    <sprite position={position} scale={[height * aspect, height, 1]} center={center} renderOrder={10} raycast={() => null}>
      <spriteMaterial map={texture} sizeAttenuation={false} depthTest={false} depthWrite={false} transparent />
    </sprite>
  )
}
