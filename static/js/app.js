/* NTTF Classroom Booking — motion enhancements
   Respects prefers-reduced-motion. No external dependencies. */

(function () {
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    /* ---------- Scroll-reveal: anything with .reveal fades up when it enters viewport ---------- */
    function initReveal() {
        const targets = document.querySelectorAll('.reveal');
        if (!targets.length) return;
        if (prefersReducedMotion || !('IntersectionObserver' in window)) {
            targets.forEach(el => el.classList.add('is-visible'));
            return;
        }
        const io = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-visible');
                    io.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
        targets.forEach(el => io.observe(el));
    }

    /* ---------- 3D tilt on cards: subtle, springy, follows the pointer ---------- */
    function initTilt() {
        if (prefersReducedMotion) return;
        const tiltables = document.querySelectorAll('.dashboard-card, [data-tilt]');
        tiltables.forEach((el) => {
            const maxTilt = 8; // degrees
            let raf = null;

            function onMove(e) {
                const rect = el.getBoundingClientRect();
                const x = (e.clientX - rect.left) / rect.width;
                const y = (e.clientY - rect.top) / rect.height;
                const rotY = (x - 0.5) * 2 * maxTilt;
                const rotX = (0.5 - y) * 2 * maxTilt;
                if (raf) cancelAnimationFrame(raf);
                raf = requestAnimationFrame(() => {
                    el.style.transform = `translateY(-10px) rotateX(${rotX.toFixed(2)}deg) rotateY(${rotY.toFixed(2)}deg)`;
                });
            }

            function onLeave() {
                if (raf) cancelAnimationFrame(raf);
                el.style.transform = '';
            }

            el.addEventListener('mousemove', onMove);
            el.addEventListener('mouseleave', onLeave);
        });
    }

    /* ---------- Ripple effect on .btn-primary / .login-btn clicks ---------- */
    function initRipple() {
        if (prefersReducedMotion) return;
        document.addEventListener('click', (e) => {
            const btn = e.target.closest('.btn-primary, .login-btn, .btn-book');
            if (!btn) return;
            const rect = btn.getBoundingClientRect();
            const ripple = document.createElement('span');
            const size = Math.max(rect.width, rect.height);
            ripple.style.cssText = `
                position: absolute;
                width: ${size}px; height: ${size}px;
                left: ${e.clientX - rect.left - size / 2}px;
                top: ${e.clientY - rect.top - size / 2}px;
                background: rgba(255, 255, 255, 0.45);
                border-radius: 50%;
                transform: scale(0);
                pointer-events: none;
                animation: ripple 0.6s ease-out forwards;
            `;
            const computed = getComputedStyle(btn);
            if (computed.position === 'static') btn.style.position = 'relative';
            btn.style.overflow = 'hidden';
            btn.appendChild(ripple);
            setTimeout(() => ripple.remove(), 650);
        });

        if (!document.getElementById('ripple-keyframes')) {
            const style = document.createElement('style');
            style.id = 'ripple-keyframes';
            style.textContent = '@keyframes ripple { to { transform: scale(2.6); opacity: 0; } }';
            document.head.appendChild(style);
        }
    }

    /* ---------- Auto-add .reveal to common content blocks ---------- */
    function autoReveal() {
        const selectors = [
            '.dashboard-card',
            '.card',
            '.booking-grid',
            '.table-responsive',
            '.page-header',
            '.hero-section'
        ];
        selectors.forEach((sel) => {
            document.querySelectorAll(sel).forEach((el, idx) => {
                if (!el.classList.contains('reveal') && !el.closest('.login-shell')) {
                    el.classList.add('reveal');
                    el.style.transitionDelay = `${Math.min(idx * 60, 240)}ms`;
                }
            });
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        autoReveal();
        initReveal();
        initTilt();
        initRipple();
    });
})();
