---
name: frontend-design
description: Create distinctive, production-grade frontend interfaces with high design quality
user_invocable: false
---

# Frontend Design

When creating or reviewing frontend code, follow these design principles to produce distinctive, polished interfaces that avoid generic "AI aesthetics."

## Design Thinking

1. **Understand the purpose** -- What emotion should the UI evoke? Who is the user?
2. **Pick a BOLD aesthetic direction** -- Do not default to "clean and modern." Choose one:
   - Minimal / Swiss / Bauhaus
   - Maximalist / Collage / Layered
   - Retro-futuristic / Y2K / Synthwave
   - Organic / Natural / Biomimicry
   - Luxury / Editorial / High-fashion
   - Playful / Rounded / Toylike
   - Brutalist / Raw / Deconstructed
   - Art Deco / Geometric / Ornate
   - Soft / Pastel / Cozy / Kawaii
   - Industrial / Technical / Monospaced
3. **Identify differentiation** -- What makes this NOT look like every other dashboard?

## Typography

- Avoid overused fonts: Arial, Helvetica, Inter, Roboto, Open Sans
- Prefer: system-ui stack, monospace for data, serif for editorial, display fonts for headers
- Use font-weight and letter-spacing for hierarchy, not just size

## Color & Theme

- Use CSS custom properties for theming
- Pick a dominant color with 1-2 sharp accent colors
- Dark mode is not just "invert everything" -- adjust contrast, saturation, elevation
- Use semantic color tokens (e.g., `--color-danger`, `--color-surface`), not raw hex

## Motion (when applicable)

- For HTML/CSS: CSS-only transitions and animations preferred
- For React: use framer-motion or Motion library
- Motion should communicate state change, not just decorate
- Keep durations under 300ms for UI transitions

## Spatial Composition

- Break the grid occasionally: asymmetry, overlap, diagonal flow
- Use whitespace aggressively -- let elements breathe
- Vary card/section sizes rather than uniform grids

## Backgrounds & Texture

- Gradient meshes, noise textures, geometric patterns
- Subtle grain overlay for depth
- Avoid: pure white (#fff) backgrounds, pure black (#000) text

## Anti-Patterns (BANNED)

- Generic card-grid layouts with rounded corners and soft shadows
- Every section looking the same
- Blue primary + gray everything else
- "Hero section with 3 feature cards below"
- Cookie-cutter SaaS dashboard look
- Placeholder "Lorem ipsum" or "Click here" text in final output

## Output Requirements

- Code must be complete and runnable
- Include realistic placeholder content, not lorem ipsum
- Test responsive behavior (mobile/tablet/desktop)
- Production-grade: proper error states, loading states, empty states
