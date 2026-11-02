// Scroll-linked layer: progress bar, format band drift, pinned story stages, copy button.
(function () {
    'use strict';
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var bar = document.querySelector('[data-progress]'), band = document.querySelector('[data-band]'),
        story = document.querySelector('[data-story]');
    var consoleEl = story && story.querySelector('[data-stage]'),
        steps = story ? story.querySelectorAll('.story-steps li') : [],
        label = story && story.querySelector('[data-stage-label]');
    var LABELS = ['Fetching', 'Writing', 'Scored'];
    var ticking = false, stage = 1;

    function update() {
        ticking = false;
        var max = document.documentElement.scrollHeight - window.innerHeight;
        if (bar) bar.style.setProperty('--p', max > 0 ? (window.scrollY / max).toFixed(4) : 0);
        if (band && !reduce) {
            var r = band.parentNode.getBoundingClientRect(), vh = window.innerHeight;
            var t = Math.min(1, Math.max(0, (vh - r.top) / (vh + r.height)));
            var travel = Math.max(0, band.scrollWidth / 2 - window.innerWidth * 0.5);
            band.style.setProperty('--bx', (t * travel).toFixed(1));
        }
        if (story) {
            var sr = story.getBoundingClientRect(), total = sr.height - window.innerHeight;
            var p = total > 0 ? Math.min(1, Math.max(0, -sr.top / total)) : 0;
            var s = p < 0.33 ? 1 : p < 0.66 ? 2 : 3;
            if (s !== stage) {
                stage = s;
                consoleEl.setAttribute('data-stage', s);
                label.textContent = LABELS[s - 1];
                steps.forEach(function (li, i) { li.classList.toggle('on', i === s - 1); });
            }
        }
    }
    function onScroll() { if (!ticking) { ticking = true; requestAnimationFrame(update); } }
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    update();

    // Choosing a step scrolls the story to that stage.
    steps.forEach(function (li, i) {
        li.tabIndex = 0;
        function go() {
            var sr = story.getBoundingClientRect(), total = sr.height - window.innerHeight;
            window.scrollTo({ top: window.scrollY + sr.top + total * (i * 0.33 + 0.12), behavior: reduce ? 'auto' : 'smooth' });
        }
        li.addEventListener('click', go);
        li.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    });

    // Copy button for the API example.
    var btn = document.querySelector('[data-copy]'), code = document.getElementById('curl');
    if (btn && code) btn.addEventListener('click', function () {
        function done() { btn.textContent = 'Copied'; setTimeout(function () { btn.textContent = 'Copy'; }, 1800); }
        if (navigator.clipboard) navigator.clipboard.writeText(code.textContent).then(done, function () { btn.textContent = 'Select and copy'; });
        else btn.textContent = 'Select and copy';
    });
})();
