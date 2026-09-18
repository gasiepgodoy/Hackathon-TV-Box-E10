# ForgeOS frontend modernization

## Scope and inspection

The requested Hackathon repository contains seven team projects. Equipe 1 owns
MultiForge: ForgeImager (React 19 / TypeScript / Vite / Tauri), ForgeOS (Python
standard-library HTTP server and a plain HTML/CSS/JavaScript portal), ForgeDB,
and Python application modules. This change targets the **ForgeOS web portal**,
the on-device interface for networking, system services, logs and applications.
The desktop flasher and other teams' applications are outside this change.

Inspection of the supplied Armbian machine found a different, compiled ForgeHub
application on port 8080 and modified MultiForge checkouts. That installation
must not be mistaken for this repository's Python portal. Work is staged in a
separate checkout; existing services and uncommitted changes are preserved.

## Plan and decisions

1. Preserve the Python server, API contracts and existing workflows. No new
   frontend framework, runtime packages, build pipeline or CDN requirement.
2. Extract the combined HTML/CSS/JavaScript file into static assets served by the
   existing `/static/` route. Keep the classic script interface temporarily so
   existing inline action handlers remain compatible.
3. Introduce a restrained visual system: system fonts, semantic color tokens,
   consistent spacing, larger targets, a welcome area, and the original logo
   presented with its natural proportions. Avoid continuous animation.
4. Restore zoom, introduce navigation landmarks/current-page state, provide
   dialog focus containment and restoration, and support directional remote
   navigation without intercepting text editing or native select controls.
5. Make unavailable telemetry explicit, respect zero measurements, and reduce
   polling to every five seconds while visible. Preserve manual refresh.
6. Verify browser behavior with mocked API responses and the actual Python
   static-file handler on Armbian. Document deployment boundaries.

## File responsibilities

| File | Responsibility |
| --- | --- |
| `web/index.html` | Semantic shell, screens, forms, dialogs and welcome content |
| `web/static/css/portal.css` | Existing components retained for compatibility; obsolete fixed-height log overrides removed |
| `web/static/css/design.css` | Visual tokens, component refinements, responsive layouts and motion preferences |
| `web/static/js/portal.js` | Existing API workflows, rendering, state and telemetry |
| `web/static/js/accessibility.js` | Shared keyboard, remote, menu and dialog focus behavior |

The stylesheet refinement layer makes the migration reviewable without a risky
rewrite of all existing components. A future change can consolidate individual
components and replace the remaining inline styles/handlers as they are touched.
The disconnected Svelte build artifacts already in `web/_app` are not used by
the current entry page; they remain for compatibility rather than being deleted
without a separate migration audit.

## Validation

From `ForgeOS/tests/e2e`:

```sh
npm ci
npx playwright install chromium
npm test
```

The frontend suite uses a local static preview and intercepted API calls. It
checks all six screens at 390, 800, 1440 and 1920 pixel widths; script errors;
horizontal overflow; quoted SSID rendering and provisioning payloads; keyboard
navigation; modal focus; theme persistence; invalid hashes; telemetry failures
and recovery; and automated WCAG A/AA checks in both themes. Screenshots are
written to the ignored `artifacts/` directory. Axe checks complement manual
review and do not constitute complete accessibility certification.

On Armbian, from `ForgeOS`:

```sh
python3 tests/frontend_smoke.py
```

This runs the real Python asset handler on an ephemeral loopback port and
checks HTML, CSS and JavaScript responses and MIME types. It does not call
network provisioning, service controls or module installation endpoints.

The legacy hardware test suite is explicitly available as `npm run test:hardware`.
It targets older selectors and can reset networking; it has not been used as
evidence for this frontend change. No application bundling step is required for
the plain-JavaScript portal. Tauri desktop builds are unaffected.

## Deployment and remaining boundaries

Deploy the updated `web/index.html` **and** the new CSS/JS files together to a
compatible ForgeOS Python portal. Replacing the Go ForgeHub binary or its
embedded React assets with these files is not a supported deployment.

Backend code is unchanged. It still contains legacy fallback hardware values,
static interface details, and restricted SSID validation (including rejection
of double quotes). Frontend quote-safe rendering does not change server-side
validation. Physical TV remote testing and real provisioning/service/module
operations remain hardware acceptance tasks; automated tests simulate those
responses to avoid interrupting the SSH connection.
