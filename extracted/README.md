# CALCULATOR WITH EXECUTION TIME

A high-performance desktop scientific calculator featuring a precision mathematical calculation engine, responsive dark glassmorphism GUI, live expression preview, interactive history drawer, and **automatic per-calculation execution time profiling and logging**.

---

## ⚡ Execution Time Profiling & Saved Metrics

Every calculation executed by the engine or through the user interface is profiled and recorded with high-resolution performance timers (`time.perf_counter_ns()`).

### 1. High-Resolution Measurement
The execution time measures the **full calculation lifecycle**:
$$\text{Tokenize} \longrightarrow \text{Recursive-Descent Parse} \longrightarrow \text{Evaluate} \longrightarrow \text{12-Digit Formatting}$$

- **No external dependencies** or slow `eval()`/`exec()` calls.
- Pure Python execution achieving an average of **~12.8 microseconds per calculation** (~78,000 calculations per second).

### 2. Live On-Screen Timing Display
Whenever a calculation is submitted in the GUI (by pressing `=` or <kbd>Enter</kbd>):
- The exact execution time is instantly calculated.
- The duration is toasted in the top-right corner of the display panel (e.g., `3.5 µs` or `0.02 ms`).

### 3. Persistent Execution Time Logs
Every single calculation performed is automatically recorded and appended to two local files:

1. **`execution_times.log`** — Formatted plain-text log:
   ```text
   [2026-10-13 19:58:58.331] Expr: 6*7                            | Result: 42              | Time:    27.10 µs (0.0271 ms)
   [2026-10-13 19:58:58.333] Expr: ans+8                          | Result: 50              | Time:    36.60 µs (0.0366 ms)
   [2026-10-13 19:58:58.333] Expr: 2+3                            | Result: 5               | Time:    24.90 µs (0.0249 ms)
   ```

2. **`execution_times.csv`** — Structured CSV log for spreadsheets and data processing:
   ```csv
   timestamp,expression,result,execution_time_us,execution_time_ms
   2026-10-13 19:58:58.331,6*7,42,27.10,0.0271
   2026-10-13 19:58:58.333,ans+8,50,36.60,0.0366
   2026-10-13 19:58:58.333,2+3,5,24.90,0.0249
   ```

---

## 📊 Benchmark Execution Times (Every Calculation Case)

The following benchmark results were measured across tens of thousands of sampled runs covering each calculation category:

<!-- BENCHMARK_TABLE_START -->

_Python 3.14.0 on Windows AMD64; 20,000 runs per row for the mean, 5,000 timed samples for median/p99._

| Case | Expression | Mean Execution Time | Median | 99th Percentile |
|---|---|---:|---:|---:|
| Simple arithmetic | `12+7` | 3.9 µs | 3.9 µs | 11.9 µs |
| Mixed precedence | `2+3*4-5/2` | 9.8 µs | 8.7 µs | 24.8 µs |
| Nested parentheses | `((2+3)*(4-1))^2/5` | 15.8 µs | 14.2 µs | 34.1 µs |
| Trigonometry (DEG) | `sin(30)+cos(60)*tan(45)` | 15.9 µs | 14.1 µs | 29.2 µs |
| Logarithms and roots | `log(1000)+ln(e)+sqrt(144)` | 14.5 µs | 13.8 µs | 28.3 µs |
| Factorial | `20!` | 5.3 µs | 5.0 µs | 12.9 µs |
| Large power | `2^100` | 6.3 µs | 5.9 µs | 11.8 µs |
| Percent | `200+10%` | 5.1 µs | 4.7 µs | 6.6 µs |
| Long expression (~60 chars) | `1+2*3-4/5+6^2-7*8+9/3+sqrt(16)*2-(3+4)*(5-2)+log(100)` | 42.1 µs | 36.0 µs | 78.8 µs |

**Average across cases:** 13.2 µs per calculation (~75,837 calculations/second)

**UI key press -> repaint latency:** mean 4.52 ms, median 4.09 ms, 99th pct 8.88 ms, worst 10.49 ms (well within the 16.7 ms 60 Hz frame budget).

<!-- BENCHMARK_TABLE_END -->

---

## 🚀 Running the Project

### Requirements
- Python 3.10+ (tested on Python 3.14)
- Standard library only (`tkinter`, `math`, `time`, `re`, `sys`) — **no external pip packages required**.

### Launch GUI
```bash
# Navigate to the project directory
cd C:\PDC\extracted

# Launch in Scientific Mode (Default)
python main.py

# Launch in Compact Basic Mode
python main.py --basic
```

### Run Benchmarks & Update README
```bash
# Run engine calculation benchmarks
python benchmark.py

# Run engine + GUI repaint latency benchmarks
python benchmark.py --ui

# Print benchmark results in Markdown format
python benchmark.py --markdown

# Re-run benchmarks and automatically update the table in this README
python benchmark.py --save-readme
```

### Run Automated Test Suite
```bash
python -m unittest test_engine.py
```
*(Runs 21 unit tests covering arithmetic, operator precedence, trigonometry, logarithms, roots, and error handling).*

---

## 🧮 Features & Syntax

| Category | Operators & Functions | Examples |
|---|---|---|
| **Basic Arithmetic** | `+`, `-` (or `−`), `*` (or `×`), `/` (or `÷`) | `12 + 8 / 4 = 14` |
| **Precedence** | Parentheses `()`, power `^` (right-associative) | `2^3^2 = 512`, `(2+3)*4 = 20` |
| **Implicit Multiplication** | Juxtaposition before parentheses & constants | `2(3+4) = 14`, `2pi = 6.28318530718` |
| **Trigonometry** | `sin`, `cos`, `tan`, `asin`, `acos`, `atan` | `sin(30) = 0.5` (in DEG mode) |
| **Hyperbolic** | `sinh`, `cosh`, `tanh` | `sinh(1) = 1.17520119364` |
| **Logarithms & Powers** | `ln`, `log`, `log10`, `log2`, `exp`, `^` | `log(100) = 2`, `ln(e) = 1` |
| **Roots** | `sqrt` (or `√`), `cbrt` (or `∛`), `root(x, n)` | `sqrt(144) = 12`, `cbrt(27) = 3` |
| **Factorial** | `n!` or `fact(n)` | `5! = 120`, `20! = 2432902008176640000` |
| **Percent** | Add/subtract percent context or fraction | `200 + 10% = 220`, `50 * 20% = 10` |
| **Angle Modes** | Toggle between `DEG` (degrees) and `RAD` (radians) | Click top-right `DEG` chip in GUI |
| **Memory Register** | `MC` (Clear), `MR` (Recall), `M+` (Add), `M-` (Subtract) | Stores running memory with `M` badge |
| **Constants** | `pi` ($\pi$), `e`, `tau` ($\tau$), `ans` (last result) | `ans + 10` reuses previous answer |

---

## 📁 Project Structure

| File | Description |
|---|---|
| `main.py` | Application entry point supporting `--basic` and default scientific layouts |
| `calculator/engine.py` | Tokenizer, recursive-descent math parser, evaluator, and execution time logger |
| `calculator/ui.py` | Dark Tkinter user interface with custom animations, history drawer, and timing toast |
| `benchmark.py` | Nanosecond precision performance benchmark suite and README table updater |
| `test_engine.py` | 21 unit tests validating calculations, precision, and edge cases |
| `execution_times.log` | Auto-generated human-readable log saving execution time for every calculation |
| `execution_times.csv` | Auto-generated CSV recording timestamp, expression, result, and execution times |
| `README.md` | Complete project documentation and verified performance report |
