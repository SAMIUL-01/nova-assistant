/* ==========================================================================
   Nova avatar  —  cute anime-style female assistant

   Drawn as inline SVG rather than an image file so it is tiny, sharp at any
   size, themeable, and animatable. Four states:

     idle       gentle float, occasional blink
     listening  glowing ring, eyes a little wider  (microphone is on)
     thinking   eyes glance up, dots orbit          (waiting for the model)
     speaking   mouth animates in time with the TTS voice

   The speaking animation is driven by the real speech events in voice.js,
   so the mouth stops exactly when the voice does.
   ========================================================================== */

window.NovaAvatar = (() => {
  "use strict";

  const SVG = `
<svg viewBox="0 0 200 200" class="nova-face" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="novaHair" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"  stop-color="#4a5fd6"/>
      <stop offset="55%" stop-color="#33409c"/>
      <stop offset="100%" stop-color="#242d6e"/>
    </linearGradient>
    <linearGradient id="novaEye" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"  stop-color="#8fd0ff"/>
      <stop offset="60%" stop-color="#3b82f6"/>
      <stop offset="100%" stop-color="#1e3a8a"/>
    </linearGradient>
    <radialGradient id="novaGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%"  stop-color="#6da8ff" stop-opacity=".55"/>
      <stop offset="100%" stop-color="#6da8ff" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <!-- aura, only visible while listening -->
  <circle class="nova-aura" cx="100" cy="104" r="86" fill="url(#novaGlow)"/>
  <circle class="nova-ring" cx="100" cy="104" r="76" fill="none"
          stroke="#6da8ff" stroke-width="2" opacity="0"/>

  <!-- hair behind -->
  <path d="M38 108c0-40 26-70 62-70s62 30 62 70c0 26-6 44-12 52 4-30-2-52-10-60
           -14 10-38 14-56 10-14-3-24-9-30-16-8 12-12 34-8 66-6-8-8-26-8-52z"
        fill="url(#novaHair)"/>

  <!-- face -->
  <ellipse class="nova-head" cx="100" cy="108" rx="46" ry="50" fill="#ffe0cf"/>
  <ellipse cx="100" cy="108" rx="46" ry="50" fill="none" stroke="#f0c4ae" stroke-width="1"/>

  <!-- ears -->
  <ellipse cx="55" cy="112" rx="7" ry="11" fill="#ffe0cf"/>
  <ellipse cx="145" cy="112" rx="7" ry="11" fill="#ffe0cf"/>

  <!-- fringe / bangs -->
  <path d="M54 100c2-34 22-56 46-56s44 22 46 56c-8-16-18-26-30-30-6 12-18 20-32 22
           -12 2-22-2-30-8-2 6-2 10 0 16z" fill="url(#novaHair)"/>
  <path d="M60 74c10-16 24-26 40-26s30 10 40 26c-12-10-25-15-40-15s-28 5-40 15z"
        fill="#5a6ee8" opacity=".55"/>

  <!-- side locks -->
  <path d="M52 96c-6 24-6 46-2 66 6-6 10-18 10-34z" fill="url(#novaHair)"/>
  <path d="M148 96c6 24 6 46 2 66-6-6-10-18-10-34z" fill="url(#novaHair)"/>

  <!-- eyebrows -->
  <path class="nova-brow" d="M74 92c5-4 13-5 18-2" stroke="#3b4bb8"
        stroke-width="3" fill="none" stroke-linecap="round"/>
  <path class="nova-brow" d="M126 92c-5-4-13-5-18-2" stroke="#3b4bb8"
        stroke-width="3" fill="none" stroke-linecap="round"/>

  <!-- eyes -->
  <g class="nova-eyes">
    <ellipse class="nova-eye" cx="82" cy="112" rx="11" ry="13" fill="url(#novaEye)"/>
    <ellipse class="nova-eye" cx="118" cy="112" rx="11" ry="13" fill="url(#novaEye)"/>
    <circle cx="78" cy="107" r="4"   fill="#ffffff" opacity=".95"/>
    <circle cx="114" cy="107" r="4"  fill="#ffffff" opacity=".95"/>
    <circle cx="86" cy="117" r="2"   fill="#ffffff" opacity=".65"/>
    <circle cx="122" cy="117" r="2"  fill="#ffffff" opacity=".65"/>
    <!-- eyelids drop down to blink -->
    <rect class="nova-lid" x="70" y="96" width="24" height="0" fill="#ffe0cf"/>
    <rect class="nova-lid" x="106" y="96" width="24" height="0" fill="#ffe0cf"/>
  </g>

  <!-- blush -->
  <ellipse cx="70" cy="128" rx="9" ry="5" fill="#ffb3c1" opacity=".55"/>
  <ellipse cx="130" cy="128" rx="9" ry="5" fill="#ffb3c1" opacity=".55"/>

  <!-- nose -->
  <path d="M100 120v5" stroke="#e8b49c" stroke-width="2" stroke-linecap="round"/>

  <!-- mouth: scaleY is animated while speaking -->
  <g class="nova-mouth-group">
    <path class="nova-mouth-smile" d="M92 136c4 4 12 4 16 0"
          stroke="#d4677f" stroke-width="3" fill="none" stroke-linecap="round"/>
    <ellipse class="nova-mouth-open" cx="100" cy="138" rx="7" ry="6" fill="#c2536c"/>
  </g>

  <!-- thinking dots -->
  <g class="nova-thoughts">
    <circle cx="150" cy="56" r="4"/>
    <circle cx="163" cy="46" r="5.5"/>
    <circle cx="178" cy="34" r="7"/>
  </g>
</svg>`;

  // Nova appears in more than one place (welcome screen + header), and every
  // copy must react to the same state. A single "root" would only animate
  // whichever one was mounted last.
  const roots = [];
  let blinkTimer = null;
  let mouthTimer = null;
  let current = "idle";

  function mount(container) {
    if (!container || roots.includes(container)) return;
    container.classList.add("nova-avatar");
    container.innerHTML = SVG;
    roots.push(container);
    setState(current);
    if (roots.length === 1) scheduleBlink();
  }

  function scheduleBlink() {
    clearTimeout(blinkTimer);
    // Humans blink irregularly; a fixed interval looks robotic.
    const wait = 2600 + Math.random() * 3800;
    blinkTimer = setTimeout(() => {
      if (current !== "thinking") {
        roots.forEach((r) => r.classList.add("blink"));
        setTimeout(() => roots.forEach((r) => r.classList.remove("blink")), 170);
      }
      scheduleBlink();
    }, wait);
  }

  function setState(next) {
    current = next;
    roots.forEach((r) => {
      r.classList.remove("is-idle", "is-listening", "is-thinking", "is-speaking");
      r.classList.add(`is-${next}`);
      r.setAttribute("data-state", next);
    });
    if (next !== "speaking") stopMouth();
  }

  /** Called on each spoken word so the mouth matches the voice. */
  function pulseMouth() {
    roots.forEach((r) => r.classList.add("mouth-open"));
    clearTimeout(mouthTimer);
    mouthTimer = setTimeout(
      () => roots.forEach((r) => r.classList.remove("mouth-open")), 110);
  }

  function stopMouth() {
    clearTimeout(mouthTimer);
    roots.forEach((r) => r.classList.remove("mouth-open"));
  }

  return { mount, setState, pulseMouth, state: () => current };
})();
