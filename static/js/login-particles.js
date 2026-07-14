/**
 * 登录页粒子连线网络背景
 * 尊重 prefers-reduced-motion，降低性能开销时自动降级
 */
(function () {
    'use strict';

    var canvas = document.getElementById('particle-canvas');
    if (!canvas) return;

    var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var ctx = canvas.getContext('2d');
    var particles = [];
    var mouse = { x: null, y: null, active: false };
    var rafId = null;
    var dpr = Math.min(window.devicePixelRatio || 1, 2);

    var CONFIG = {
        count: reduceMotion ? 28 : 70,
        maxDist: 140,
        mouseDist: 160,
        speed: reduceMotion ? 0.15 : 0.35,
        color: '6, 182, 212',
        radius: [1.2, 2.4]
    };

    function resize() {
        var w = window.innerWidth;
        var h = window.innerHeight;
        canvas.width = Math.floor(w * dpr);
        canvas.height = Math.floor(h * dpr);
        canvas.style.width = w + 'px';
        canvas.style.height = h + 'px';
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function createParticles() {
        particles = [];
        var w = window.innerWidth;
        var h = window.innerHeight;
        for (var i = 0; i < CONFIG.count; i++) {
            particles.push({
                x: Math.random() * w,
                y: Math.random() * h,
                vx: (Math.random() - 0.5) * CONFIG.speed,
                vy: (Math.random() - 0.5) * CONFIG.speed,
                r: CONFIG.radius[0] + Math.random() * (CONFIG.radius[1] - CONFIG.radius[0])
            });
        }
    }

    function dist(a, b) {
        var dx = a.x - b.x;
        var dy = a.y - b.y;
        return Math.sqrt(dx * dx + dy * dy);
    }

    function draw() {
        var w = window.innerWidth;
        var h = window.innerHeight;
        ctx.clearRect(0, 0, w, h);

        for (var i = 0; i < particles.length; i++) {
            var p = particles[i];
            p.x += p.vx;
            p.y += p.vy;

            if (p.x < 0 || p.x > w) p.vx *= -1;
            if (p.y < 0 || p.y > h) p.vy *= -1;
            p.x = Math.max(0, Math.min(w, p.x));
            p.y = Math.max(0, Math.min(h, p.y));

            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(' + CONFIG.color + ', 0.85)';
            ctx.fill();
        }

        for (var a = 0; a < particles.length; a++) {
            for (var b = a + 1; b < particles.length; b++) {
                var d = dist(particles[a], particles[b]);
                if (d < CONFIG.maxDist) {
                    var alpha = 1 - d / CONFIG.maxDist;
                    ctx.beginPath();
                    ctx.moveTo(particles[a].x, particles[a].y);
                    ctx.lineTo(particles[b].x, particles[b].y);
                    ctx.strokeStyle = 'rgba(' + CONFIG.color + ', ' + (alpha * 0.35) + ')';
                    ctx.lineWidth = 1;
                    ctx.stroke();
                }
            }

            if (mouse.active) {
                var dm = dist(particles[a], mouse);
                if (dm < CONFIG.mouseDist) {
                    var ma = 1 - dm / CONFIG.mouseDist;
                    ctx.beginPath();
                    ctx.moveTo(particles[a].x, particles[a].y);
                    ctx.lineTo(mouse.x, mouse.y);
                    ctx.strokeStyle = 'rgba(' + CONFIG.color + ', ' + (ma * 0.45) + ')';
                    ctx.lineWidth = 1.2;
                    ctx.stroke();
                }
            }
        }

        rafId = requestAnimationFrame(draw);
    }

    function onMove(e) {
        mouse.x = e.clientX;
        mouse.y = e.clientY;
        mouse.active = true;
    }

    function onLeave() {
        mouse.active = false;
    }

    function onResize() {
        resize();
        createParticles();
    }

    resize();
    createParticles();
    draw();

    window.addEventListener('mousemove', onMove, { passive: true });
    window.addEventListener('mouseleave', onLeave);
    window.addEventListener('resize', onResize);

    window.addEventListener('beforeunload', function () {
        if (rafId) cancelAnimationFrame(rafId);
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseleave', onLeave);
        window.removeEventListener('resize', onResize);
    });
})();
