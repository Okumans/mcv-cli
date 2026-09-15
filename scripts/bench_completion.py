#!/usr/bin/env python3

import os
import shutil
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

MCV = os.environ.get("MCV_BIN") or shutil.which("mcv")
RUNS = int(os.environ.get("RUNS", "10"))

if not MCV:
    raise SystemExit("mcv was not found; set MCV_BIN=/path/to/mcv")


def benchmark(label, args, variables, runs=RUNS):
    env = os.environ.copy()
    env.update(variables)

    samples = []

    for _ in range(runs):
        start = time.perf_counter_ns()
        result = subprocess.run(
            [MCV, *args],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        elapsed = (time.perf_counter_ns() - start) / 1_000_000
        samples.append(elapsed)

        if result.returncode != 0:
            raise RuntimeError(f"{label} failed:\n{result.stderr}")

    print(
        f"{label:<28} "
        f"median={statistics.median(samples):7.2f} ms "
        f"min={min(samples):7.2f} ms "
        f"max={max(samples):7.2f} ms"
    )


protocols = {
    "bash": {
        "_MCV_COMPLETE": "complete_bash",
        "COMP_WORDS": "mcv courses 21",
        "COMP_CWORD": "2",
    },
    "zsh": {
        "_MCV_COMPLETE": "complete_zsh",
        "_TYPER_COMPLETE_ARGS": "mcv courses 21",
    },
    "fish": {
        "_MCV_COMPLETE": "complete_fish",
        "_TYPER_COMPLETE_ARGS": "mcv courses 21",
        "_TYPER_COMPLETE_FISH_ACTION": "get-args",
    },
    "powershell": {
        "_MCV_COMPLETE": "complete_powershell",
        "_TYPER_COMPLETE_ARGS": "mcv courses 21",
        "_TYPER_COMPLETE_WORD_TO_COMPLETE": "21",
    },
}

for shell, variables in protocols.items():
    benchmark(f"{shell} protocol", [], variables)
    benchmark(f"{shell} --completion", ["--completion"], variables)


fish = shutil.which("fish")
if fish:
    fish_env = os.environ.copy()
    fish_env["PATH"] = f"{Path(MCV).parent}:{fish_env.get('PATH', '')}"

    script = subprocess.check_output(
        [MCV, "--show-completion", "fish"],
        env=fish_env,
        text=True,
    )

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".fish",
        delete=False,
        encoding="utf-8",
    ) as file:
        file.write(script)
        script_path = file.name

    try:
        fish_command = (
            f"source {script_path}; "
            "complete -C 'mcv courses 21' >/dev/null"
        )

        samples = []
        for _ in range(RUNS):
            start = time.perf_counter_ns()
            result = subprocess.run(
                [fish, "--no-config", "-c", fish_command],
                env=fish_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            samples.append((time.perf_counter_ns() - start) / 1_000_000)

            if result.returncode != 0:
                raise RuntimeError(result.stderr)

        print(
            f"{'fish actual completion':<28} "
            f"median={statistics.median(samples):7.2f} ms "
            f"min={min(samples):7.2f} ms "
            f"max={max(samples):7.2f} ms"
        )
    finally:
        Path(script_path).unlink(missing_ok=True)
