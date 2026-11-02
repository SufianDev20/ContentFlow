// Landing page behaviour: format tabs, local thread preview, panel notes, entrances.
(function () {
    'use strict';

    // Example data for one sample article. Numbers are an example run, not live stats.
    var SAMPLE = {
        tweet: { items: [
            '1/4 We cut our deploy from 40 minutes to 6. No new tools, just three boring changes. A thread:',
            '2/4 First, we stopped rebuilding the base image on every push. Cache it, pin it, rebuild weekly.',
            '3/4 Second, tests run in parallel by service instead of one long queue. The slowest suite now sets the clock.',
            '4/4 Third, we deploy the diff, not the whole system. Less to ship, less to break. Full write-up in the post.'
        ], lat: '3.2 s', tok: '412', tps: '129', q: 88 },
        linkedin: { items: [
            'Our deploys used to take 40 minutes. Last month they took 6.',
            'We did not adopt a new platform. We made three changes that sound boring and added up fast.',
            'We stopped rebuilding the base image on every push. We run tests in parallel by service. We deploy only what changed.',
            'The surprise was the team. With a 6 minute deploy, people ship smaller changes more often, and review gets easier.',
            'What is the slowest step in your pipeline that nobody has questioned in a year?'
        ], lat: '4.1 s', tok: '512', tps: '125', q: 84 },
        email: { sub: 'Subject: How we cut deploys from 40 minutes to 6', items: [
            'Hi there,',
            'Our deploys used to take 40 minutes, and last month they took 6. It took three changes and no new tools.',
            'We cached the base image, ran tests in parallel by service, and deployed only the diff. Read the full post for the details and the numbers.',
            'Reply and tell me which of the three you would try first.'
        ], lat: '4.8 s', tok: '602', tps: '125', q: 81 },
        tldr: { items: [
            'A team cut deploy time from 40 minutes to 6 by caching the base image, running tests in parallel by service, and shipping only the diff.'
        ], lat: '1.6 s', tok: '168', tps: '105', q: 91 }
    };

    function renderOut(out, key) {
        var d = SAMPLE[key];
        out.textContent = '';
        var n = 0;
        if (d.sub) {
            var s = document.createElement('p');
            s.className = 'o sub'; s.style.setProperty('--n', n++); s.textContent = d.sub;
            out.appendChild(s);
        }
        d.items.forEach(function (t) {
            var p = document.createElement('p');
            p.className = 'o'; p.style.setProperty('--n', n++); p.textContent = t;
            out.appendChild(p);
        });
    }

    function renderMetrics(root, key) {
        var d = SAMPLE[key], dd = root.querySelectorAll('dd');
        dd[0].textContent = d.lat; dd[1].textContent = d.tok; dd[2].textContent = d.tps;
        if (dd[3]) dd[3].textContent = d.q;
    }

    function wireTabs(scope, onChange) {
        var tabs = Array.prototype.slice.call(scope.querySelectorAll('[role="tab"]'));
        function select(tab, focus) {
            tabs.forEach(function (t) { t.setAttribute('aria-selected', t === tab ? 'true' : 'false'); t.tabIndex = t === tab ? 0 : -1; });
            if (focus) tab.focus();
            onChange(tab.getAttribute('data-format'));
        }
        tabs.forEach(function (tab, i) {
            tab.tabIndex = tab.getAttribute('aria-selected') === 'true' ? 0 : -1;
            tab.addEventListener('click', function () { select(tab, false); });
            tab.addEventListener('keydown', function (e) {
                var k = e.key, j = -1;
                if (k === 'ArrowRight') j = (i + 1) % tabs.length;
                else if (k === 'ArrowLeft') j = (i - 1 + tabs.length) % tabs.length;
                else if (k === 'Home') j = 0;
                else if (k === 'End') j = tabs.length - 1;
                if (j > -1) { e.preventDefault(); select(tabs[j], true); }
            });
        });
    }

    // Hero composer
    var comp = document.querySelector('[data-composer]');
    if (comp) {
        var cOut = comp.querySelector('[data-out]'), cMet = comp.querySelector('[data-metrics]');
        wireTabs(comp, function (key) { renderOut(cOut, key); renderMetrics(cMet, key); });
    }

    // Panel with notes
    var panel = document.querySelector('[data-panel]');
    if (panel) {
        var pOut = panel.querySelector('[data-out]'), pMet = panel.querySelector('[data-metrics]'),
            pQ = panel.querySelector('[data-q]'), pBar = panel.querySelector('[data-qbar]');
        wireTabs(panel, function (key) {
            renderOut(pOut, key); renderMetrics(pMet, key);
            pQ.textContent = SAMPLE[key].q; pBar.style.width = SAMPLE[key].q + '%';
        });
        var prov = panel.querySelector('[data-provider]');
        panel.querySelector('[data-model]').addEventListener('change', function (e) {
            prov.textContent = e.target.value === 'gemini' ? 'Gemini' : 'OpenRouter first, Gemini as fallback';
        });
        var parts = panel.querySelectorAll('[data-part]');
        function focusPart(id) {
            parts.forEach(function (p) { p.classList.toggle('dim', !!id && p.getAttribute('data-part') !== id); });
        }
        document.querySelectorAll('.n').forEach(function (n) {
            var id = n.getAttribute('data-for');
            n.addEventListener('mouseenter', function () { focusPart(id); });
            n.addEventListener('mouseleave', function () { focusPart(null); });
            n.addEventListener('focus', function () { focusPart(id); });
            n.addEventListener('blur', function () { focusPart(null); });
        });
    }

    // Local thread preview: cut text into tweets of up to 270 characters on sentence edges.
    var draft = document.getElementById('draft'), cards = document.querySelector('[data-cards]'),
        count = document.querySelector('[data-count]');
    function splitThread(text) {
        var sentences = text.replace(/\s+/g, ' ').trim().match(/[^.!?]+[.!?]*/g) || [];
        var out = [], cur = '';
        sentences.forEach(function (s) {
            s = s.trim();
            if (!s) return;
            if (cur && (cur + ' ' + s).length > 262) { out.push(cur); cur = s; }
            else cur = cur ? cur + ' ' + s : s;
        });
        if (cur) out.push(cur);
        return out;
    }
    function renderThread() {
        var parts = splitThread(draft.value), total = parts.length;
        cards.textContent = '';
        parts.forEach(function (t, i) {
            var li = document.createElement('li'), p = document.createElement('p'), s = document.createElement('small');
            var full = (i + 1) + '/' + total + ' ' + t;
            p.textContent = full;
            s.textContent = full.length + ' of 280 characters';
            if (full.length > 280) s.className = 'warn';
            li.appendChild(p); li.appendChild(s); cards.appendChild(li);
        });
        count.textContent = total + (total === 1 ? ' tweet' : ' tweets');
    }
    if (draft && cards) { draft.addEventListener('input', renderThread); renderThread(); }

    // Closing form: carry the email into registration (handled by the GET form itself).
    var cta = document.querySelector('[data-cta]');
    if (cta) cta.addEventListener('submit', function () {
        var f = cta.querySelector('input');
        if (f.value === 'you@example.com') f.value = '';
    });

    // Entrances, once per element.
    var targets = document.querySelectorAll('[data-reveal]');
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!('IntersectionObserver' in window) || reduce) {
        targets.forEach(function (el) { el.classList.add('in'); });
    } else {
        var io = new IntersectionObserver(function (es) {
            es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
        }, { threshold: 0, rootMargin: '0px 0px -8% 0px' });
        targets.forEach(function (el) { io.observe(el); });
    }
})();
