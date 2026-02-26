export default function AboutPage() {
    return (
        <main className="about-page">
            <section className="about-card">
                <h2>About Kalitron Edge</h2>
                <p>
                    Kalitron Edge is a quantitative engine for event markets.
                    It combines probabilistic signals, risk guardrails, and
                    execution telemetry to support discretionary and automated
                    workflows.
                </p>
                <p>
                    The platform separates signal detection from execution so
                    analytics can explain what was detected, what was blocked,
                    and what was actually traded.
                </p>
            </section>

            <section className="about-card">
                <h3>Methodology (High Level)</h3>
                <ul>
                    <li>Quant model computes side probabilities per event slot.</li>
                    <li>Quant gate filters by sample, edge, and market context.</li>
                    <li>Kelly sizing computes stake with configurable caps.</li>
                    <li>Risk guards enforce cooldowns and exposure limits.</li>
                </ul>
            </section>

            <section className="about-card">
                <h3>Risk Notice</h3>
                <p>
                    Trading event markets involves financial risk. Past
                    performance does not guarantee future results. Use position
                    limits and conservative sizing.
                </p>
            </section>

            <section className="about-card">
                <h3>Contact</h3>
                <div className="about-contact-list">
                    <a href="mailto:outis10@gmail.com">outis10@gmail.com</a>
                    <a href="mailto:janodelgadillo@hotmail.com">
                        janodelgadillo@hotmail.com
                    </a>
                </div>
            </section>
        </main>
    );
}
