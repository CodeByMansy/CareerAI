const canvas = document.getElementById("background");
const ctx = canvas.getContext("2d");

let particles = [];
let width = 0;
let height = 0;
let mouse = { x: null, y: null };

function resizeCanvas() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;

    const count = Math.min(90, Math.floor((width * height) / 14000));

    particles = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.35,
        radius: Math.random() * 1.6 + 0.6
    }));
}

function drawBackground() {
    ctx.clearRect(0, 0, width, height);

    particles.forEach((particle, index) => {
        particle.x += particle.vx;
        particle.y += particle.vy;

        if (particle.x < 0 || particle.x > width) particle.vx *= -1;
        if (particle.y < 0 || particle.y > height) particle.vy *= -1;

        if (mouse.x !== null && mouse.y !== null) {
            const dx = particle.x - mouse.x;
            const dy = particle.y - mouse.y;
            const distance = Math.sqrt(dx * dx + dy * dy);

            if (distance < 120 && distance > 0) {
                particle.x += (dx / distance) * 0.35;
                particle.y += (dy / distance) * 0.35;
            }
        }

        ctx.beginPath();
        ctx.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(160, 150, 255, 0.7)";
        ctx.fill();

        for (let j = index + 1; j < particles.length; j++) {
            const other = particles[j];
            const dx = particle.x - other.x;
            const dy = particle.y - other.y;
            const distance = Math.sqrt(dx * dx + dy * dy);

            if (distance < 115) {
                ctx.beginPath();
                ctx.moveTo(particle.x, particle.y);
                ctx.lineTo(other.x, other.y);
                ctx.strokeStyle = `rgba(115, 125, 235, ${0.14 * (1 - distance / 115)})`;
                ctx.lineWidth = 0.7;
                ctx.stroke();
            }
        }
    });

    requestAnimationFrame(drawBackground);
}

window.addEventListener("resize", resizeCanvas);

window.addEventListener("mousemove", (event) => {
    mouse.x = event.clientX;
    mouse.y = event.clientY;
});

window.addEventListener("mouseleave", () => {
    mouse.x = null;
    mouse.y = null;
});

resizeCanvas();
drawBackground();