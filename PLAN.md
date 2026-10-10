# PLAN: Animated login screen

The login and loading screens become one dark screen with the teaser's animated
MetaList logo. The form (namespace picker, password) and, after the password is
accepted, the loading progress sit under the logo; the logo never moves.

## Decisions (agreed)
- Logo: the teaser's block **M** over two bars, with the **MetaList** wordmark under it
  (as in `media/metalist-teaser.mp4`, 0–2.3 s). Rebuilt as inline SVG + code-driven
  animation (sharp at any size, ~2 KB, can jump to its final frame).
- **Dark only** for now (white on near-black, as in the teaser).
- **Remove the old intro video** from the app: `app/static/video/login-startup.mp4`,
  `STARTUP_ANIMATION_ENABLED`, `CONFIG.STARTUP.ENABLE_LOGIN_INTRO`, the startup
  splash and its code/CSS/tests/docs (git history keeps it).
- The screen only changes once the password is **accepted**; a wrong password never
  slides anything.

## The animation (from the teaser, 6 fps frames)
| Time | What happens |
|------|--------------|
| 0.0–0.3 s | Empty dark screen |
| 0.3–0.6 s | Lower bar fades in |
| 0.5–0.9 s | Upper bar slides in from the right and settles |
| 1.0–1.7 s | The M drops in from above, fading in, overshoots slightly and settles on the bars |
| 1.8–2.3 s | "MetaList" fades in under the mark |

Total ≈ 2.3 s. Afterwards the logo is static in that final frame. Driven by one
pure function of time (`logoFrame(t)` → positions/opacities), so tests can check
exact frames and "jump to the end" is `logoFrame(end)`.

## Screen layout
- Logo centred, large: mark about 160 px wide on a desktop window (scales down on
  narrow windows), wordmark under it.
- Under the logo, one panel area the logo's width:
  - **Form view:** namespace picker (when there are several namespaces), password
    field, OK button, error line.
  - **Loading view:** a progress bar exactly the logo's width; under it, in grey
    italics, the current step ("Decrypting notes into memory"). Nothing else (no
    title, no "first load" line, no elapsed time).
- Background: the teaser's near-black with its soft radial glow.

## Cases (interaction principles: to approve before code)
Principle: keep the point of attention (the logo) still; only the user's action
changes the screen (pressing OK); the minimum motion.

| # | Case | Result |
|---|------|--------|
| 1 | Open the login page | The logo animates once (2.3 s); the form is there from the start, focus in the password field |
| 2 | Type and press OK (Enter) | Nothing moves. The OK button shows "Checking…" and is disabled |
| 3 | Wrong password | The error appears under the field; the field is cleared and focused. Nothing moved |
| 4 | Too many attempts (rate limit) | The server's message appears like case 3 |
| 5 | Password accepted | The form slides left out of the panel area while the loading view slides in from the right (≈350 ms, ease-out). The logo does not move |
| 6 | Accepted while the logo is still animating (very fast typing) | The animation continues uninterrupted; the slide happens under it |
| 7 | First login after an update (backup and database upgrade) | The server says beforehand whether an upgrade is pending (new `/auth/status` field). If so, the button reads "Checking…" and a grey italic line under it says "Backing up and upgrading this namespace…" until the password is accepted |
| 8 | Loading progresses | The bar fills (no width jumps backwards); the grey line shows the current step |
| 9 | Loading done | The app appears as today |
| 10 | Loading fails | The error replaces the grey line, loudly (red), and stays; as today the app does not open |
| 11 | Switch namespace in the picker | As today (new tab and namespace loading page); this plan does not change that page |
| 12 | No login screen needed (no password, or already logged in, notes in memory) | As today: the app appears directly, with no logo screen (it would only flash for under a second) |
| 13 | The browser asks for reduced motion (system setting) | The logo is shown static in its final frame; the slide becomes an instant swap |
| 14 | Window too narrow | The logo and panel scale down together; the bar stays the logo's width |

**Fitting the animation:** it starts when the page opens, and the logo stays put
through the slide, so loading never interrupts it. The app itself can only appear
after a password is typed and checked, which takes longer than 2.3 s. Case 12 is
the only fast path and shows no logo screen at all. So no runtime estimate is
needed; if one ever is, the rule is: show the final frame when the app is ready
before the animation would end.

## Server
- `/auth/status` gains `database_upgrade_pending: bool` (required): the namespace's
  database version is older than `CURRENT_DATABASE_VERSION` (an upgrade runs at the
  next login). No schema change.
- Remove `STARTUP_ANIMATION_ENABLED` and the template flag.

## Browser
- `app/templates/index.html`: new login markup (logo SVG, panel with form and
  loading views); remove the video, splash and old loading texts.
- `app/static/js/modules/login-logo-animation.js` (new): `logoFrame(t)`, playing it
  with `requestAnimationFrame`, `showFinalFrame()`, reduced-motion handling.
- `auth.js`: busy button and upgrade note (cases 2–4, 7), slide on success (5),
  loading view updates (8, 10); remove the intro-video waiting and the elapsed
  timer.
- `main.css`: the dark login screen, logo sizing, the slide, the progress bar.

## Tests
- JS unit:
  - `logoFrame` at exact times (start, each phase boundary, end, after end);
  - cases 2–5 and 7 on the form state;
  - progress never going backwards (case 8);
  - reduced motion (case 13).
- Update `login_progress_flow.test.mjs`, `session_identity_login.test.mjs` and others
  that reference the old panel, timer or video.
- Python: `database_upgrade_pending` true and false; the removed flag is gone from
  config and templates.
- Browser suite (Chrome and Firefox):
  - wrong password keeps the form in place with the error;
  - a correct password slides to loading with the logo at the exact same position
    (bounding box before and after);
  - the bar's width equals the logo's;
  - the app opens.
- Full Python (3.12 and 3.10) and JS suites, and both sanity gates.

## Docs and help
- `docs/ui/` login/startup docs (find the right file; propose one if none fits), `README.md` if it
  mentions the intro video, `docs/AI-SUMMARY.md`, `app/services/agent/skills/`
  where the login screen or `STARTUP_ANIMATION_ENABLED` is described.

## Order (one behavior at a time; you try each)
1. The dark screen with the animated logo and the form (cases 1–4, 13, 14); old video removed.
2. Upgrade note (7) and the slide into the loading view (5, 6, 8–10).
