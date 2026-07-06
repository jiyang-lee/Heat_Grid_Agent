# HeatGrid Ops Simulation Design System

## 1. Atmosphere & Identity

A quiet operations console for studying one priority card at a time. The signature is restrained evidence: compact panels, clear status chips, and JSON surfaces that make the model input visible without turning the page into a developer tool.

## 2. Color

### Palette

| Role | Token | Light | Usage |
|---|---|---|---|
| Surface/primary | `--surface-primary` | `#f7f8fb` | Page background |
| Surface/secondary | `--surface-secondary` | `#ffffff` | Panels |
| Surface/elevated | `--surface-elevated` | `#f1f4f8` | Code blocks |
| Text/primary | `--text-primary` | `#172033` | Main text |
| Text/secondary | `--text-secondary` | `#5b667a` | Supporting text |
| Border/default | `--border-default` | `#d8deea` | Panel borders |
| Accent/primary | `--accent-primary` | `#2563eb` | Primary action |
| Accent/hover | `--accent-hover` | `#1d4ed8` | Button hover |
| Status/success | `--status-success` | `#15803d` | Connected |
| Status/warning | `--status-warning` | `#b45309` | Missing optional service |
| Status/error | `--status-error` | `#b91c1c` | Failed service |

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Usage |
|---|---:|---:|---:|---|
| H1 | 28px | 700 | 1.2 | Page title |
| H2 | 18px | 700 | 1.3 | Panel title |
| Body | 15px | 400 | 1.6 | Main copy |
| Body/sm | 13px | 400 | 1.5 | Secondary info |
| Caption | 12px | 600 | 1.4 | Labels |

### Font Stack

- Primary: `Segoe UI, system-ui, -apple-system, sans-serif`
- Mono: `Cascadia Mono, Consolas, monospace`

## 4. Spacing & Layout

### Base Unit

All spacing uses a 4px base.

| Token | Value | Usage |
|---|---:|---|
| `--space-2` | 8px | Tight gaps |
| `--space-3` | 12px | Inputs |
| `--space-4` | 16px | Panel inner gaps |
| `--space-6` | 24px | Panel padding |
| `--space-8` | 32px | Major gaps |

### Grid

- Max content width: 1180px
- Main layout: responsive two-column operations console
- Breakpoint: below 860px, stack panels vertically

## 5. Components

### Panel

- Structure: section with header and body
- Variants: standard, code
- Spacing: `--space-6`
- States: default only
- Accessibility: heading is visible and semantic
- Motion: none

### Status Chip

- Structure: inline status text with tonal background
- Variants: success, warning, error
- Spacing: `--space-2` horizontal padding
- States: default
- Accessibility: text label does not rely on color alone
- Motion: none

### Primary Button

- Structure: native button
- Variants: primary
- Spacing: `--space-3` vertical, `--space-4` horizontal
- States: default, hover, active, disabled
- Accessibility: visible focus ring, disabled state
- Motion: transform on active only

## 6. Motion & Interaction

| Type | Duration | Easing | Usage |
|---|---:|---|---|
| Micro | 120ms | ease-out | Button hover/active |

Motion is minimal because this is an operational tool. Interactive elements show hover, active, focus, and disabled states.

## 7. Depth & Surface

Strategy: borders-only with tonal code surfaces. Panels use `--border-default` and a subtle radius of 8px.
