# Easy UI Quality Standard

Easy uses a quiet operational UI standard for board work. The goal is fast scanning, reliable interaction, and accessibility before decoration.

## Baseline

- Use [WCAG 2.2](https://www.w3.org/TR/WCAG22/) AA as the accessibility baseline for text contrast, focus visibility, labels, keyboard access, dragging alternatives, and target size.
- Use progressive disclosure for secondary creation and administration forms. Follow the [USWDS accordion pattern](https://designsystem.digital.gov/components/accordion/) principle that a clear trigger hides or reveals related content.
- Keep motion short and purposeful. Use [Material Design motion duration/easing](https://m3.material.io/styles/motion/easing-and-duration) as the reference for responsive, bounded transitions.
- Prefer dense but legible work surfaces over marketing-style composition.
- Keep operational surfaces neutral: plain app background, white panels, restrained blue/teal accents, and status colors only when they communicate state.
- Keep cards, panels, inputs, and buttons at `8px` border radius or less.
- Avoid decorative gradients, oversized type inside work surfaces, nested cards, and purely ornamental shadows.
- Keep operational text letter spacing at `0`; do not compensate for cramped layouts with negative tracking or decorative uppercase tracking.
- Preserve keyboard movement for cards with `Alt+Arrow` and pointer movement within and between lists.

## Board Interaction Requirements

- Drag targets must remain usable when a list is empty.
- Dropping a card must persist on the drop event and restore the card if saving fails.
- Dragging must not accidentally navigate to the card detail page.
- Focus states must be visible on cards and controls.
- Desktop and mobile views must not create document-level horizontal overflow.
- Board creation, list creation, list actions, and card creation must be hidden behind explicit disclosure triggers until requested.
- Disclosure triggers must be reachable, focusable, and at least `32px` tall in the rendered UI.
- Transitions on cards, controls, and disclosure triggers must stay at or below `250ms` and must not depend on delayed animation.

## E2E Gate

Run:

```powershell
npm run qa:ui-quality
```

The gate starts a real Django board and checks:

- desktop and mobile overflow
- visible card focus state
- minimum operational control size
- empty-list drop-zone size
- card text contrast at WCAG AA threshold
- operational border radius at `8px` or less
- plain app background for the work surface
- progressive disclosure behavior for creation/action forms
- neutral operational letter spacing
- bounded interaction motion

Run it with the normal checks before release:

```powershell
npm run qa:dragdrop
npm run qa:frontend
npm run qa:ui-quality
```
