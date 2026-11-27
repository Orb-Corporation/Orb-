#!/usr/bin/env python3
"""Compare Orb! with GCC using output-checked, interleaved median timings.

Usage: python3 bench/run.py [fib sieve matmul collatz mandel] [--samples 7]
       python3 bench/run.py --reference-orb path/to/base/orb --samples 7
"""
import argparse
import os
import shlex
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
ROOT = BENCH_DIR.parent
ORB = ROOT / "build" / ("orb.exe" if os.name == "nt" else "orb")
DEFAULTS = ("fib", "sieve", "matmul", "collatz", "mandel")
C_VARIANTS = (("gcc -O0", "-O0"), ("gcc -O2", "-O2"))


def invoke(command, timeout):
    try:
        result = subprocess.run(
            command, cwd=BENCH_DIR, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode("utf-8", errors="replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = error.stderr.decode("utf-8", errors="replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
        raise RuntimeError(
            "timed out after %ds: %s\nstdout:\n%s\nstderr:\n%s"
            % (timeout, " ".join(map(str, command)), stdout, stderr)
        ) from error
    if result.returncode:
        raise RuntimeError(
            "exit code %d: %s\nstdout:\n%s\nstderr:\n%s"
            % (result.returncode, " ".join(map(str, command)), result.stdout, result.stderr)
        )
    return result.stdout


def build_variants(name, output_dir, cc, timeout, compilers):
    source_orb = BENCH_DIR / (name + ".orb")
    source_c = BENCH_DIR / (name + ".c")
    if not source_orb.is_file() or not source_c.is_file():
        raise RuntimeError("benchmark needs both %s.orb and %s.c" % (name, name))

    binaries = {}
    for label, compiler in compilers:
        if not compiler.is_file():
            raise RuntimeError("Orb compiler not found at %s" % compiler)
        for variant, flags in ((label, []), (label + " --unchecked", ["--unchecked"])):
            binary = output_dir / ("%s-%s" % (name, variant.replace(" ", "-")))
            invoke([compiler, "build", source_orb, *flags, "-o", binary], timeout)
            binaries[variant] = binary

    for label, optimization in C_VARIANTS:
        binary = output_dir / ("%s-%s" % (name, label.replace(" ", "-")))
        invoke([*cc, optimization, "-o", binary, source_c, "-lm"], timeout)
        binaries[label] = binary
    return binaries


def time_program(binary, expected, timeout):
    start = time.perf_counter()
    output = invoke([binary], timeout)
    elapsed = time.perf_counter() - start
    if output != expected:
        raise RuntimeError(
            "%s printed different output\nexpected: %r\nactual:   %r"
            % (binary, expected, output)
        )
    return elapsed


def benchmark(name, samples, timeout, cc, reference_orb=None):
    compilers = []
    if reference_orb is not None:
        compilers.append(("orb-base", reference_orb))
        compilers.append(("orb-current", ORB))
    else:
        compilers.append(("orb", ORB))
    variant_names = tuple(
        label for compiler, _ in compilers
        for label in (compiler, compiler + " --unchecked")
    ) + tuple(label for label, _ in C_VARIANTS)

    with tempfile.TemporaryDirectory(prefix="orb-bench-") as temp:
        binaries = build_variants(name, Path(temp), cc, timeout, compilers)

        # Warm each executable and check all variants against GCC -O2.
        outputs = {label: invoke(binary, timeout) for label, binary in binaries.items()}
        expected = outputs["gcc -O2"]
        for label, output in outputs.items():
            if output != expected:
                raise RuntimeError(
                    "%s output mismatch\nGCC -O2: %r\n%s: %r"
                    % (name, expected, label, output)
                )

        timings = {label: [] for label in variant_names}
        for round_index in range(samples):
            offset = round_index % len(variant_names)
            order = variant_names[offset:] + variant_names[:offset]
            for label in order:
                timings[label].append(time_program(binaries[label], expected, timeout))

    medians = {label: statistics.median(values) for label, values in timings.items()}
    return medians, expected.strip()


def print_single(name, medians, output):
    ratio = medians["orb"] / medians["gcc -O2"] if medians["gcc -O2"] else float("inf")
    print("%-10s %9.3fs %13.3fs %9.3fs %9.3fs %9.2fx   %s" % (
        name, medians["orb"], medians["orb --unchecked"],
        medians["gcc -O0"], medians["gcc -O2"], ratio, output
    ))


def print_paired(name, medians, output):
    base = medians["orb-base"]
    current = medians["orb-current"]
    change = (current / base - 1.0) * 100.0 if base else float("inf")
    print("%-10s %9.3fs %11.3fs %12.3fs %14.3fs %9.3fs %9.3fs %+8.1f%%   %s" % (
        name, base, current,
        medians["orb-base --unchecked"], medians["orb-current --unchecked"],
        medians["gcc -O0"], medians["gcc -O2"], change, output
    ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmarks", nargs="*", help="benchmark names (default: all)")
    parser.add_argument("--samples", type=int, default=7, help="timed runs per variant (default: 7)")
    parser.add_argument("--timeout", type=int, default=120, help="seconds per compile or run")
    parser.add_argument("--cc", default=os.environ.get("CC", "gcc"), help="C compiler command")
    parser.add_argument("--reference-orb", type=Path, help="base-branch Orb compiler for a paired comparison")
    args = parser.parse_args()
    if args.samples < 1 or args.timeout < 1:
        parser.error("--samples and --timeout must be positive")
    names = args.benchmarks or DEFAULTS
    cc = shlex.split(args.cc)
    if not cc:
        parser.error("--cc must name a compiler")
    reference_orb = args.reference_orb.resolve() if args.reference_orb else None
    if reference_orb is not None and not reference_orb.is_file():
        parser.error("--reference-orb does not point to a compiler file")

    if reference_orb is None:
        print("Interleaved median of %d runs; every variant's output is checked." % args.samples)
        print("%-10s %10s %14s %10s %10s %10s   %s" % (
            "benchmark", "orb", "orb-unchecked", "gcc -O0", "gcc -O2", "orb/O2", "output"
        ))
    else:
        print("Paired interleaved medians (%d runs per variant); every output is checked." % args.samples)
        print("%-10s %9s %11s %12s %14s %9s %9s %9s   %s" % (
            "benchmark", "base orb", "current orb", "base unchecked",
            "current unchecked", "gcc -O0", "gcc -O2", "change", "output"
        ))

    for name in names:
        medians, output = benchmark(name, args.samples, args.timeout, cc, reference_orb)
        if reference_orb is None:
            print_single(name, medians, output)
        else:
            print_paired(name, medians, output)


if __name__ == "__main__":
    main()
