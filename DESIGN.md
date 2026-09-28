---
version: alpha
name: AOS Dispatch Manifest
description: A code-led operations system built from cool label stock, freight routing, and physical governance stamps.
colors:
  primary: "#1746a2"
  primary-deep: "#103375"
  primary-soft: "#dce7fb"
  ink: "#142131"
  ink-soft: "#34465a"
  muted: "#59697a"
  paper: "#f4f7f9"
  label: "#ffffff"
  line: "#bdc9d5"
  line-strong: "#7d8fa3"
  amber: "#9a5a00"
  amber-bg: "#fff0c7"
  red: "#a62e32"
  red-bg: "#fde7e8"
  green: "#176b43"
  green-bg: "#dcf3e7"
  focus: "#ffbf2f"
typography:
  display:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "4.2rem"
    fontWeight: 700
    lineHeight: 1.04
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "2.35rem"
    fontWeight: 700
    lineHeight: 1.04
    letterSpacing: "-0.035em"
  title:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "1rem"
    fontWeight: 700
    lineHeight: 1.04
    letterSpacing: "0.005em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
  small-copy:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.8rem"
    fontWeight: 400
    lineHeight: 1.55
  status-label:
    fontFamily: "Barlow Condensed, sans-serif"
    fontSize: "0.74rem"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.055em"
  mono:
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, Liberation Mono, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.65
rounded:
  stamp: "2px"
  sm: "4px"
  md: "9px"
  lg: "18px"
  round: "999px"
spacing:
  xs: "0.35rem"
  sm: "0.55rem"
  md: "0.8rem"
  lg: "1rem"
  xl: "1.25rem"
  2xl: "2rem"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.label}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "0.62rem 0.9rem"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.primary-deep}"
    textColor: "{colors.label}"
  button-secondary:
    backgroundColor: "{colors.label}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "0.62rem 0.9rem"
    height: "44px"
  button-danger:
    backgroundColor: "{colors.red}"
    textColor: "{colors.label}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "0.62rem 0.9rem"
    height: "44px"
  dispatch-hero:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.label}"
    rounded: "{rounded.lg}"
    padding: "clamp(1.2rem, 4vw, 2.25rem)"
  manifest-panel:
    backgroundColor: "{colors.label}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "1rem"
  status-stamp-amber:
    backgroundColor: "{colors.amber-bg}"
    textColor: "{colors.amber}"
    typography: "{typography.status-label}"
    rounded: "{rounded.stamp}"
    padding: "0.14rem 0.46rem"
    height: "24px"
  status-stamp-red:
    backgroundColor: "{colors.red-bg}"
    textColor: "{colors.red}"
    typography: "{typography.status-label}"
    rounded: "{rounded.stamp}"
    padding: "0.14rem 0.46rem"
    height: "24px"
  status-stamp-green:
    backgroundColor: "{colors.green-bg}"
    textColor: "{colors.green}"
    typography: "{typography.status-label}"
    rounded: "{rounded.stamp}"
    padding: "0.14rem 0.46rem"
    height: "24px"
  input:
    backgroundColor: "{colors.label}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "0.65rem 0.7rem"
    height: "44px"
  notice-information:
    backgroundColor: "{colors.primary-soft}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0.8rem 0.9rem"
  document-frame:
    backgroundColor: "{colors.label}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "clamp(1rem, 3vw, 1.5rem)"
---

# Design System: AOS Dispatch Manifest

## Overview

**Creative North Star: "The Dispatch Manifest"**

AOS presents commissioned work as freight moving through accountable checkpoints. The visual language is code-led and operational: cool label stock, freight blue fields, deep ink, clipped shipping-label corners, registration crosses, fixed progress routes, and physical status stamps. It avoids the generic software-dashboard look without sacrificing scanability or server-rendered restraint.

Governance is visible structure rather than decoration. Progress, holds, review, and release occupy stable positions; semantic colors reinforce words and shapes instead of replacing them. Desktop layouts support oversight and careful review, while mobile layouts preserve the same route logic in a vertical sequence.

**Key Characteristics:**
- Cool, lightly industrial label-stock surfaces rather than warm paper or glossy glass.
- Freight blue establishes movement and primary action; deep ink carries operational authority.
- Clipped corners, fine rules, registration marks, route nodes, and stamped labels create the physical manifest character.
- Amber, green, and red are reserved for waiting/review, release/approval, and hold/rejection semantics.
- Motion is brief, state-specific, and absent when reduced motion is requested.

## Colors

The palette is a cool operational system: freight blue provides identity and action, deep blue-black neutrals support dense reading, and semantic colors mark governance events.

### Primary

- **Freight Blue** (`primary`, #1746a2): broad identity fields, completed route segments, and primary actions.
- **Deep Freight Blue** (`primary-deep`, #103375): primary hover states and text-selection contrast.
- **Transit Wash** (`primary-soft`, #dce7fb): informational notice bands and low-emphasis operational context.

### Secondary

- **Safety Amber** (`amber`, #9a5a00) with **Amber Stock** (`amber-bg`, #fff0c7): waiting, pending review, local-development warnings, and signature attention.
- **Hold Red** (`red`, #a62e32) with **Red Stock** (`red-bg`, #fde7e8): blocked work, failed runs, rejection, integrity holds, and destructive action.
- **Release Green** (`green`, #176b43) with **Green Stock** (`green-bg`, #dcf3e7): approval and releasable state.
- **Inspection Yellow** (`focus`, #ffbf2f): keyboard focus and the current checkpoint node.

### Neutral

- **Deep Ink** (`ink`, #142131): primary text, active route outlines, and high-authority labels.
- **Soft Ink** (`ink-soft`, #34465a): completed-but-secondary route text.
- **Manifest Gray** (`muted`, #59697a): metadata, identity text, and explanatory copy.
- **Cool Label Stock** (`paper`, #f4f7f9): application background.
- **Fresh Label** (`label`, #ffffff): panels, controls, summary slips, and document surfaces.
- **Rule Line** (`line`, #bdc9d5) and **Strong Rule** (`line-strong`, #7d8fa3): separation, input outlines, route scaffolding, and document framing.

### Named Rules

**The Semantic Reserve Rule.** Amber, red, and green belong to governance state; do not spend them on general decoration.

**The Redundancy Rule.** Every meaningful status combines color with explicit text and, where applicable, a distinct route-node or stamp shape.

## Typography

- **Display Font:** Barlow Condensed (with sans-serif fallback)
- **Body Font:** Native system sans (`-apple-system`, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial)
- **Label/Mono Font:** Barlow Condensed for stamps; UI monospace for checksums, errors, and artifact text

**Character:** Barlow Condensed gives headings and stamps the compact authority of freight labeling. The native system face keeps operational prose fast and familiar, while monospace is limited to byte-bound or machine-reported material.

### Hierarchy

- **Display** (700, `clamp(2rem, 6vw, 4.2rem)`, 1.04): the blue dispatch field and rare identity-scale statements.
- **Headline** (700, `clamp(1.5rem, 3.3vw, 2.35rem)`, 1.04): task and artifact titles.
- **Title** (700, `1rem`, 1.04): section heads, panel heads, and compact hierarchy labels.
- **Body** (400, `15px`, 1.55): operational descriptions and forms; prose is generally capped near 72 characters.
- **Small Copy** (400, `0.8rem`, 1.55): metadata, provenance, qualification, and guidance.
- **Status Label** (700, `0.74rem`, `0.055em`, uppercase): physical status stamps and semantic tags.
- **Mono** (400, `13px`, 1.65): checksums, errors, file previews, and machine output.

### Named Rules

**The Condensed Authority Rule.** Use Barlow Condensed for headings and status hardware, not for paragraphs or long review text.

**The Machine Evidence Rule.** Monospace identifies exact bytes or machine reports; it is not a decorative coding motif.

## Layout

The application sits in a centered container capped at 1180px with a minimum 1rem desktop gutter. Core operational pages use unequal two-column grids: active work or review content receives the broad column, while exception, manifest, and decision panels occupy a quieter rail. The principal gaps are 1rem to 1.25rem, with 2rem to 2.4rem separating larger sections.

Route strips use five fixed, equal checkpoint cells on wider screens. At 560px and below, they become a vertical route without changing checkpoint order. At 820px and below, queue, task, and review shells collapse to one column; artifact metadata leads, the reviewed document follows, and the decision panel remains last. Controls retain a 44px minimum touch height.

**Known responsive limitation:** on a 390px viewport, some unusually long task, guardrail, or run text can still clip at the right edge. This is an accepted shipping limitation in the current implementation, not a reusable design-system rule.

**The Stable Checkpoint Rule.** Progress labels keep a predictable order and position so operators compare tasks without relearning the route.

## Elevation & Depth

The system is flat by default. Borders, clipped corners, color fields, and overlapping label-like surfaces create most hierarchy. A single low structural shadow (`0 10px 28px rgba(20, 33, 49, 0.11)`) lifts the dispatch summary and reviewed document; dialogs use a stronger interruption shadow (`0 20px 60px rgba(20, 33, 49, 0.25)`). Stamps use a faint inset highlight to suggest printed stock rather than floating glass.

### Shadow Vocabulary

- **Structural Lift** (`0 10px 28px rgba(20, 33, 49, 0.11)`): dispatch summaries and document frames only.
- **Modal Interruption** (`0 20px 60px rgba(20, 33, 49, 0.25)`): blocking notice dialogs.
- **Stamp Impression** (`inset 0 0 0 1px rgba(255, 255, 255, 0.38)`): status stamps and tags.

### Named Rules

**The Flat Manifest Rule.** Ordinary panels remain border-led and shadowless; elevation is reserved for an artifact being inspected or an interruption demanding response.

## Shapes

Most controls and panels use tight 4px corners. Secondary containers and summaries use 9px corners, while the large dispatch field uses 18px upper corners and 4px lower corners. Manifest panels and task leads clip the upper-right corner by 10–12px, with a small registration cross near that cut. Status stamps use 2px corners and a slight negative rotation; held route nodes become red diamonds rather than circles. Circular forms are reserved for route nodes and the back control. The AOS mark is a compact asymmetric droplet made from three round corners and one 8px corner.

**The Cut Label Rule.** The clipped upper-right corner belongs to manifest-like content containers; do not apply it to every control or notice.

**The Shape Carries State Rule.** Current, completed, and held checkpoints remain distinguishable through node size, border, and geometry even without color.

## Components

### Buttons

- **Shape:** compact label control with a 4px corner and 44px minimum height.
- **Primary:** freight blue with white text, a matching border, and `0.62rem 0.9rem` padding; hover deepens to Deep Freight Blue.
- **Secondary:** Fresh Label with Deep Ink text and a Strong Rule outline; hover darkens the outline.
- **Danger:** Hold Red with white text; used only for rejection or destructive action.
- **Focus / Active:** every variant receives a 3px Inspection Yellow focus outline with 3px offset; active controls shift down by 1px.

### Status Stamps and Tags

- **Style:** Barlow Condensed uppercase, 1.5px current-color border, 2px corners, slight counterclockwise rotation, and a subtle inset impression.
- **State:** amber, red, and green combine semantic stock backgrounds with explicit words. Neutral stamps use Deep Ink on Fresh Label.
- **Motion:** stamps enter once over 280ms with a firm overshoot only when reduced motion is not requested.

### Cards / Containers

- **Corner Style:** 4px baseline with a clipped 10px upper-right corner for manifest panels.
- **Background:** Fresh Label over Cool Label Stock.
- **Shadow Strategy:** none for ordinary panels; structural lift only for inspected documents and dispatch summaries.
- **Border:** 1px Rule Line, with a registration cross near the clipped corner.
- **Internal Padding:** usually 1rem, reduced to `0.82rem` on narrow screens.

### Inputs / Fields

- **Style:** Fresh Label background, Deep Ink text, Strong Rule border, 4px corner, and 44px minimum height.
- **Focus:** the global 3px Inspection Yellow outline with 3px offset.
- **Error / Disabled:** errors use Red Stock with Hold Red text and border; disabled buttons retain state but reduce opacity to 0.5.

### Navigation

The top row is intentionally compact rather than a full app bar. The asymmetric AOS mark and Barlow Condensed wordmark sit opposite identity and high-value actions. At 560px and below, the header becomes one column and keeps actions left-aligned. Back navigation is a 40px circular outlined control adjacent to a wrapping title.

### Route Strip

A five-cell ordered route is the signature component. Completed cells fill their nodes and connector in Freight Blue; the current cell enlarges into an Inspection Yellow node with a Deep Ink ring; a hold interrupts the route with a red diamond. A running task emits one restrained 800ms scan pulse when motion is allowed. On narrow screens the same route rotates into a vertical timeline.

### Dispatch Hero

The broad Freight Blue field establishes the active-work context. Its high-contrast display title, pale blue supporting copy, white summary slip, and partial circular registration graphic create one strong first-view anchor without turning the rest of the page into a marketing surface.

### Document Frame

Reviewed artifact content sits on Fresh Label with a Strong Rule outline and Structural Lift shadow. Monospace content wraps defensively and becomes a contained, scrollable region on mobile so the decision controls remain reachable.

## Do's and Don'ts

### Do:

- **Do** present work as a route with stable checkpoints, explicit labels, and visible interruptions.
- **Do** reserve Freight Blue for identity, primary action, and completed movement.
- **Do** pair every amber, red, or green state with plain-language status text.
- **Do** keep review metadata, checksum, artifact contents, and the decision control visually connected.
- **Do** preserve 44px touch targets, visible focus, semantic structure, and reduced-motion behavior.
- **Do** use clipped corners and registration details selectively to reinforce manifest-like containers.

### Don't:

- **Don't** replace the system with a generic sidebar, KPI-card grid, glossy glass, or soft consumer-dashboard aesthetic.
- **Don't** use semantic amber, red, or green as decoration or category color.
- **Don't** imply that worker completion, human approval, and release readiness are the same event.
- **Don't** animate continuously; route pulses and stamp transitions are brief, state-bound, and reduced-motion safe.
- **Don't** spread condensed or monospace typography into long-form operational reading.
- **Don't** treat the accepted 390px text-clipping limitation as permission to introduce clipping in new work.
