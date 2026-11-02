// Scroll-reveal for .reveal elements (all pages) and parallax orb drift (landing page only).
// No-ops entirely if the user has prefers-reduced-motion enabled.
(function () {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        document.querySelectorAll('.reveal').forEach(function (el) {
            el.classList.add('is-visible');
        });
        return;
    }

    var revealTargets = document.querySelectorAll('.reveal');
    if (revealTargets.length) {
        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-visible');
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });

        revealTargets.forEach(function (el) {
            observer.observe(el);
        });
    }

    var heroBg = document.querySelector('.hero-parallax-bg');
    if (heroBg) {
        var ticking = false;
        window.addEventListener('scroll', function () {
            if (!ticking) {
                window.requestAnimationFrame(function () {
                    var offset = window.scrollY * 0.25;
                    heroBg.style.transform = 'translateY(' + offset + 'px)';
                    ticking = false;
                });
                ticking = true;
            }
        }, { passive: true });
    }
})();