/*
  Terminal spinner engine.

  A global, frame-based animator that can render multi-character frames. One
  loop drives every `.spinner` on the page; it re-queries the DOM each tick, so
  spinners injected later by SSE swaps (the heartbeat status line, section
  cards, party panel) animate without any re-attachment.

  Color is always the element's CSS color (a single calm muted tone — see the
  base stylesheet). No color cycling: Consermo's loading language is a quiet
  sentence, not a light show.

  Per-element opt-in (attribute on the `.spinner` span):
    data-anim="<theme>"   pick a frame set (default below)
*/
(function () {
  // Keep every frame in a theme the SAME visible width so the text that
  // follows the spinner doesn't jitter. Quiet sets only: a braille pulse
  // and a sweep bar. Any legacy data-anim value falls back to the default.
  var THEMES = {
    pulse: ["⠁", "⠉", "⠙", "⠹", "⠸", "⠴", "⠦", "⠇"],     // braille spin
    sweep: ["[▰▱▱▱]", "[▰▰▱▱]", "[▰▰▰▱]", "[▰▰▰▰]"],       // progress sweep
  };
  var DEFAULT = "pulse";
  var tick = 0;

  function frameFor(theme) {
    var frames = THEMES[theme] || THEMES[DEFAULT];
    return frames[tick % frames.length];
  }

  function paint() {
    tick++;
    var els = document.getElementsByClassName("spinner");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      el.textContent = frameFor(el.getAttribute("data-anim") || DEFAULT);
    }
  }

  // Respect reduced-motion: hold a single frame.
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) {
    document.addEventListener("DOMContentLoaded", paint);
    paint();
  } else {
    setInterval(paint, 120);
    paint();
  }
})();
