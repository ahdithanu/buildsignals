# Accessibility statement

DealSignal is committed to making our platform usable by people with
disabilities. This statement describes our current conformance status and
contact path for accessibility feedback.

**Last updated:** 2026-07-29
**Applies to:** DealSignal web application (app.dealsignal.com)

---

## Conformance status

DealSignal targets **WCAG 2.1 Level AA** conformance. We are in active
improvement toward that goal:

| Area | Status |
|------|--------|
| Keyboard navigation (tables, modals) | Improved — Deal Inbox / Top Opportunities rows focusable |
| Form labels and ARIA names | Improved — Add Deal modal, header controls |
| Color contrast | Under review |
| Screen reader testing | Partial — VoiceOver/axe checks on key flows |

Automated checks run via ESLint jsx-a11y rules and manual axe DevTools passes
documented in [VALIDATION.md](../VALIDATION.md) §2.

---

## Known limitations

- Complex data tables may require additional screen-reader announcements for
  sort state and row actions.
- Map components (parcel discovery) rely on visual interaction; textual
  alternatives for map-only data are being expanded.
- Third-party chart libraries may not expose full ARIA semantics.

---

## Feedback and accommodations

If you encounter an accessibility barrier:

1. Email **accessibility@dealsignal.com** [CONFIGURE: replace with real inbox]
2. Include the page URL, browser/assistive technology, and steps to reproduce.
3. We aim to respond within **5 business days**.

For urgent access issues affecting an active deal workflow, contact your
DealSignal account manager or support channel.

---

## Technical specifications

- Web: HTML, WAI-ARIA, CSS, JavaScript (React)
- Tested browsers: recent Chrome, Firefox, Safari, Edge
- Assistive technologies tested: VoiceOver (macOS), NVDA (Windows, spot checks)

---

## Assessment approach

We evaluate accessibility through:

1. Design and code review (jsx-a11y, focus management)
2. Manual keyboard-only testing on critical flows
3. Automated scanning (axe DevTools, Lighthouse) before releases
4. User feedback incorporation

See [enterprise_readiness.md](enterprise_readiness.md) (J6, H1) for roadmap items.
