/*
  Terminal spinner engine.

  Replaces the single CSS braille glyph with a global, frame-based animator that
  can render multi-character / 2x2 / shape frames and cycle color. One loop
  drives every `.spinner` on the page; it re-queries the DOM each tick, so
  spinners injected later by SSE swaps (the heartbeat status line, section
  cards, party panel) animate without any re-attachment.

  Per-element opt-ins (attributes on the `.spinner` span):
    data-anim="<theme>"   pick a frame set (default below)
    data-color="off"      keep the CSS color, skip the rainbow cycle
*/
(function () {
  // Keep every frame in a theme the SAME visible width so the text that
  // follows the spinner doesn't jitter.
  var THEMES = {
    bars:     ["▁▃▅▇", "▃▅▇▅", "▅▇▅▃", "▇▅▃▁", "▅▃▁▃", "▃▁▃▅"], // ▁▃▅▇ equalizer
    orbit:    ["▖", "▘", "▝", "▗"],                 // ▖▘▝▗ 2x2 corner orbit
    stars:    ["✦", "✧", "⋆", "✧"],                 // ✦✧⋆ twinkle
    hearts:   ["♡", "♥", "♡", "♥"],                 // ♡♥ pulse
    diamonds: ["◇", "◈", "◆", "◈"],                 // ◇◈◆ pulse
    sweep:    ["[▰▱▱▱]", "[▰▰▱▱]", "[▰▰▰▱]", "[▰▰▰▰]"], // [▰▱▱▱] progress
    pulse:    ["⠁", "⠉", "⠙", "⠹", "⠸", "⠴", "⠦", "⠇"], // braille spin
  };
  var DEFAULT = "stars";
  var tick = 0;

  function frameFor(theme) {
    var frames = THEMES[theme] || THEMES[DEFAULT];
    return frames[tick % frames.length];
  }

  function paint() {
    tick++;
    var hue = (tick * 7) % 360; // full color cycle ~ every 6s at 120ms/tick
    var els = document.getElementsByClassName("spinner");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      el.textContent = frameFor(el.getAttribute("data-anim") || DEFAULT);
      if (el.getAttribute("data-color") !== "off") {
        // offset each spinner's hue a little so multiple on screen differ
        el.style.color = "hsl(" + ((hue + i * 40) % 360) + ", 72%, 70%)";
      }
    }
  }

  // Respect reduced-motion: hold a single frame, no color churn.
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) {
    document.addEventListener("DOMContentLoaded", paint);
    paint();
  } else {
    setInterval(paint, 120);
    paint();
  }
})();
