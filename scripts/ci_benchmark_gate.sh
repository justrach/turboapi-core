#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: $0 <base-commit-sha>" >&2
    exit 2
fi

base_sha="$1"
if [[ ! "$base_sha" =~ ^[0-9a-fA-F]{40}$ ]] || [[ "$base_sha" =~ ^0+$ ]]; then
    echo "FAIL: base commit must be a non-zero, full Git SHA" >&2
    exit 2
fi

repo_root="$(git rev-parse --show-toplevel)"
temp_root="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
base_worktree="$(mktemp -d "${temp_root%/}/turboapi-core-base.XXXXXX")"
artifact_dir="$(mktemp -d "${temp_root%/}/turboapi-core-bench.XXXXXX")"
base_binary="$artifact_dir/base-benchmark"
candidate_binary="$artifact_dir/candidate-benchmark"
base_zig="${BASE_ZIG:-zig}"
candidate_zig="${CANDIDATE_ZIG:-zig}"

cleanup() {
    git -C "$repo_root" worktree remove --force "$base_worktree" >/dev/null 2>&1 || true
    rmdir "$base_worktree" >/dev/null 2>&1 || true
    rm -f "$base_binary" "$candidate_binary"
    rmdir "$artifact_dir" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! git -C "$repo_root" cat-file -e "${base_sha}^{commit}"; then
    echo "FAIL: base commit $base_sha is not available locally" >&2
    exit 2
fi

git -C "$repo_root" worktree add --detach "$base_worktree" "$base_sha" >/dev/null

base_zig_version="$("$base_zig" version)"
candidate_zig_version="$("$candidate_zig" version)"
echo "Base compiler: $base_zig_version"
echo "Candidate compiler: $candidate_zig_version"

"$base_zig" build-exe "$base_worktree/bench_adversarial.zig" \
    -OReleaseFast -lc -femit-bin="$base_binary"
"$candidate_zig" build-exe "$repo_root/bench_adversarial.zig" \
    -OReleaseFast -lc -femit-bin="$candidate_binary"

run_sample() {
    local label="$1"
    local binary="$2"
    local output
    local ns

    output="$("$binary" 2>&1)"

    if ! grep -q "PASS.*all correctness checks passed" <<<"$output"; then
        printf '%s\n' "$output" >&2
        echo "FAIL: $label correctness check failed" >&2
        return 1
    fi

    if ! grep -q "matches=60000000 misses=5000000" <<<"$output"; then
        printf '%s\n' "$output" >&2
        echo "FAIL: $label match/miss count is wrong" >&2
        return 1
    fi

    ns="$(
        grep "Anti-DCE" -A 1 <<<"$output" \
            | grep "ns avg" \
            | sed -n 's/.*[[:space:]]\([0-9][0-9]*\)ns avg/\1/p'
    )"
    if [[ ! "$ns" =~ ^[0-9]+$ ]]; then
        printf '%s\n' "$output" >&2
        echo "FAIL: could not extract $label benchmark result" >&2
        return 1
    fi

    echo "$label: ${ns}ns per lookup" >&2
    printf '%s\n' "$ns"
}

median_of_three() {
    printf '%s\n' "$@" | sort -n | sed -n '2p'
}

declare -a base_samples=()
declare -a candidate_samples=()

for round in 1 2 3; do
    echo "Benchmark round $round/3" >&2
    if ((round % 2 == 1)); then
        base_samples+=("$(run_sample "base" "$base_binary")")
        candidate_samples+=("$(run_sample "candidate" "$candidate_binary")")
    else
        candidate_samples+=("$(run_sample "candidate" "$candidate_binary")")
        base_samples+=("$(run_sample "base" "$base_binary")")
    fi
done

base_median="$(median_of_three "${base_samples[@]}")"
candidate_median="$(median_of_three "${candidate_samples[@]}")"
maximum_ns="$(((base_median * 110 + 99) / 100))"

echo "Base samples: ${base_samples[*]}ns; median=${base_median}ns"
echo "Candidate samples: ${candidate_samples[*]}ns; median=${candidate_median}ns"
echo "Allowed candidate median: ${maximum_ns}ns (base median +10%, rounded up)"

if ((candidate_median > maximum_ns)); then
    echo "FAIL: router benchmark regressed by more than 10%" >&2
    exit 1
fi

echo "PASS: candidate benchmark is within 10% of its base commit"
