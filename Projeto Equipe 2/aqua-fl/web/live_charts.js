(function () {
    const plot = { x: 70, y: 22, width: 800, height: 190 };
    let currentPeriod = "live";

    function pointsFor(values, min, max) {
        return values.map((value, index) => {
            const x = plot.x + index * (plot.width / Math.max(values.length - 1, 1));
            const bounded = Math.max(min, Math.min(max, value));
            const y = plot.y + plot.height - ((bounded - min) / (max - min)) * plot.height;
            return [x, y];
        });
    }

    function updateCharts(payload) {
        const samples = currentPeriod === "live" ? payload.samples : payload[currentPeriod];
        if (!samples) return;

        document.querySelectorAll(".live-chart").forEach((chart) => {
            const key = chart.dataset.key;
            const min = Number(chart.dataset.min);
            const max = Number(chart.dataset.max);
            const unit = chart.dataset.unit || "";
            const values = samples
                .map((sample) => Number(sample[key]))
                .filter((value) => Number.isFinite(value));

            if (values.length < 2) return;

            const points = pointsFor(values, min, max);
            const polyline = chart.querySelector(".metric-line");
            const lastPoint = chart.querySelector(".last-point");
            const lastLabel = chart.querySelector(".last-label");
            const current = chart.querySelector(".live-current");

            polyline.setAttribute("points", points.map((point) => point.join(",")).join(" "));
            const last = values[values.length - 1];
            const [lastX, lastY] = points[points.length - 1];
            lastPoint.setAttribute("cx", lastX.toFixed(1));
            lastPoint.setAttribute("cy", lastY.toFixed(1));
            lastLabel.setAttribute("x", (lastX - 10).toFixed(1));
            lastLabel.setAttribute("y", (lastY - 14).toFixed(1));
            lastLabel.textContent = `${last.toFixed(2)}${unit}`;
            current.textContent = `${last.toFixed(2)}${unit}`;
        });
    }

    function refresh() {
        fetch(`/edgebox_history.json?t=${Date.now()}`, { cache: "no-store" })
            .then((response) => response.json())
            .then(updateCharts)
            .catch(() => {});
    }

    document.querySelectorAll(".history-period").forEach((button) => {
        button.addEventListener("click", () => {
            currentPeriod = button.dataset.period;
            document.querySelectorAll(".history-period").forEach((item) => item.classList.remove("active"));
            button.classList.add("active");
            refresh();
        });
    });

    refresh();
    setInterval(refresh, 2000);
})();