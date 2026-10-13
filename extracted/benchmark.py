"""Measure execution time per calculation.

    python benchmark.py            # engine only (no display needed)
    python benchmark.py --ui       # also measure key-press -> repainted UI latency
    python benchmark.py --markdown # print the tables as Markdown (used in README)

Engine timing covers the FULL pipeline: tokenise -> parse -> evaluate -> format.
"""
import gc
import platform
import statistics
import sys
import time

from calculator.engine import Calculator

CASES = [
    ("Simple arithmetic", "12+7"),
    ("Mixed precedence", "2+3*4-5/2"),
    ("Nested parentheses", "((2+3)*(4-1))^2/5"),
    ("Trigonometry (DEG)", "sin(30)+cos(60)*tan(45)"),
    ("Logarithms and roots", "log(1000)+ln(e)+sqrt(144)"),
    ("Factorial", "20!"),
    ("Large power", "2^100"),
    ("Percent", "200+10%"),
    ("Long expression (~60 chars)", "1+2*3-4/5+6^2-7*8+9/3+sqrt(16)*2-(3+4)*(5-2)+log(100)"),
]
N_MEAN, N_SAMPLES = 20_000, 5_000


def bench_engine():
    calc = Calculator(auto_save_timing=False)
    rows = []
    for label, expr in CASES:
        for _ in range(500):  # warm-up
            calc.calculate(expr)
        gc.collect()
        t0 = time.perf_counter_ns()
        for _ in range(N_MEAN):
            calc.calculate(expr)
        mean_us = (time.perf_counter_ns() - t0) / N_MEAN / 1000
        samples = []
        for _ in range(N_SAMPLES):
            a = time.perf_counter_ns()
            calc.calculate(expr)
            samples.append((time.perf_counter_ns() - a) / 1000)
        samples.sort()
        rows.append((label, expr, mean_us, statistics.median(samples), samples[int(0.99 * len(samples))]))
    return rows


def bench_ui(presses=400):
    """Time from a key press until the display is fully repainted."""
    import tkinter as tk
    from calculator.ui import App

    root = tk.Tk()
    app = App(root)
    for _ in range(30):
        root.update()
    plan = ["sin", "3", "0", "+", "(", "4", "×", "2", "5", ")", "÷", "2", "AC"]
    times = []
    for i in range(presses):
        key = plan[i % len(plan)]
        t0 = time.perf_counter_ns()
        app.press(key)
        root.update_idletasks()  # force the canvas to repaint
        times.append((time.perf_counter_ns() - t0) / 1_000_000)
    root.destroy()
    times.sort()
    return statistics.mean(times), statistics.median(times), times[int(0.99 * len(times))], max(times)


def update_readme_benchmarks(rows, env, ui_stats=None):
    """Update execution time tables in README.md."""
    import os
    overall = statistics.mean(r[2] for r in rows)
    md_table = [
        f"_{env}; {N_MEAN:,} runs per row for the mean, {N_SAMPLES:,} timed samples for median/p99._\n",
        "| Case | Expression | Mean Execution Time | Median | 99th Percentile |",
        "|---|---|---:|---:|---:|",
    ]
    for label, expr, mean, med, p99 in rows:
        md_table.append(f"| {label} | `{expr}` | {mean:.1f} µs | {med:.1f} µs | {p99:.1f} µs |")
    md_table.append(f"\n**Average across cases:** {overall:.1f} µs per calculation (~{1e6 / overall:,.0f} calculations/second)\n")
    if ui_stats:
        mean, med, p99, worst = ui_stats
        md_table.append(f"**UI key press -> repaint latency:** mean {mean:.2f} ms, median {med:.2f} ms, 99th pct {p99:.2f} ms, worst {worst:.2f} ms (well within the 16.7 ms 60 Hz frame budget).\n")
    table_content = "\n".join(md_table)

    here = os.path.dirname(os.path.abspath(__file__))
    readme_paths = [os.path.join(here, "README.md"), os.path.join(os.path.dirname(here), "README.md")]
    for path in readme_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            start_tag = "<!-- BENCHMARK_TABLE_START -->"
            end_tag = "<!-- BENCHMARK_TABLE_END -->"
            if start_tag in content and end_tag in content:
                before = content.split(start_tag)[0]
                after = content.split(end_tag)[1]
                new_content = f"{before}{start_tag}\n\n{table_content}\n{end_tag}{after}"
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"Updated benchmark results in: {path}")


def main():
    md = "--markdown" in sys.argv
    save_readme = "--save-readme" in sys.argv
    rows = bench_engine()
    env = f"Python {platform.python_version()} on {platform.system()} {platform.machine()}"
    if md:
        print(f"_{env}; {N_MEAN:,} runs per row for the mean, {N_SAMPLES:,} timed samples for median/p99._\n")
        print("| Case | Expression | Mean | Median | 99th pct |\n|---|---|---:|---:|---:|")
        for label, expr, mean, med, p99 in rows:
            print(f"| {label} | `{expr}` | {mean:.1f} µs | {med:.1f} µs | {p99:.1f} µs |")
    else:
        print(env)
        print(f"{'Case':32}{'Mean µs':>10}{'Median µs':>12}{'p99 µs':>10}")
        for label, _, mean, med, p99 in rows:
            print(f"{label:32}{mean:>10.1f}{med:>12.1f}{p99:>10.1f}")
    overall = statistics.mean(r[2] for r in rows)
    print(f"\nAverage across cases: {overall:.1f} µs per calculation (~{1e6 / overall:,.0f} calculations/second)")

    ui_stats = None
    if "--ui" in sys.argv or save_readme:
        try:
            ui_stats = bench_ui()
            mean, med, p99, worst = ui_stats
            print(f"\nUI key press -> repaint: mean {mean:.2f} ms, median {med:.2f} ms, p99 {p99:.2f} ms, worst {worst:.2f} ms")
            print("(a 60 Hz screen refreshes every 16.7 ms; anything below that is invisible)")
        except Exception as exc:  # no display available
            print(f"\nUI benchmark skipped: {exc}")

    if save_readme:
        update_readme_benchmarks(rows, env, ui_stats)


if __name__ == "__main__":
    main()
