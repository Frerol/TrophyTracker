# Retrocheevos visual identity

The 1.1.0 refresh keeps the Retrocheevos name and introduces an R-shaped
controller, an achievement check and a coral sparkle. The shared header pairs
the emblem with a text wordmark, keeping the name sharp at different scales.

- `assets/logo.png`: header emblem.
- `assets/icon.png`: square desktop and AppImage icon, also resampled by Qt.
- Ink background: `#0b1120`; raised surfaces: `#111b2b`.
- Mint accent: `#6ce7c4`; coral accent: `#ff957f`.
- Theme implementation: `src/retrocheevos/gui/styles.py`.
- [Home preview](previews/home-1.1.0.png) uses fictional account and progress data.

Persistent Home, Library, Lists and Settings navigation exposes the primary
destinations. Settings separates accounts, emulators and profile synchronization.
Scrollable pages retain access to content on shorter displays.

## Asset generation

Mode: built-in `image_gen`, iterative image editing. The final generated asset
is saved as both PNG paths above. The final prompt was:

> Finalize this same R/controller/checkmark/coral-spark emblem as an opaque desktop app icon. Replace ALL transparent regions and ALL black regions, including the controller's negative-space opening and surrounding canvas, with a single perfectly uniform solid dark ink background #101826. This opaque solid background is essential; there must be no transparency anywhere. Clean all speckled edge artifacts. Keep the emblem the same recognizable design but scale the whole emblem to 74 percent of the square so it has comfortable even margins. Use clean solid mint #6CE7C4 for the R and controls and solid coral #FF957F for the check and sparkle, no texture, grain, gradients, glow or shading. Smooth crisp vector-style edges. Flat premium app icon on a plain dark square. No text, no other objects, no mockup, no drop shadow. Square 1024x1024.
