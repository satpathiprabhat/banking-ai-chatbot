cat > /tmp/find_numpy_offenders.py <<'PY'
#!/usr/bin/env python3
import sys, subprocess, traceback, importlib, pkgutil, os

py = sys.executable
print("Python executable:", py)
print("pip freeze (top 200 lines):")
try:
    reqs = subprocess.check_output([py, "-m", "pip", "freeze"], stderr=subprocess.DEVNULL).decode().splitlines()
    for r in reqs[:200]:
        print("  ", r)
except Exception as e:
    print("Could not run pip freeze:", e)

print("\nScanning imports for failures... (this may take a minute)\n")
failures = []

# Build candidate list: try package names from pip freeze, plus a few likely modules
candidates = []
try:
    for r in reqs:
        name = r.split("==")[0].split(">=")[0].split("<")[0].strip()
        if name:
            candidates.append(name)
except Exception:
    pass

# also try top-level importable package names from installed distributions
for m in pkgutil.iter_modules():
    candidates.append(m.name)

# dedupe and sort
candidates = sorted(set(candidates))

for name in candidates:
    # skip trivial single-letter names or clearly non-importable tokens
    if len(name) < 2 or name.startswith('-'):
        continue
    # try to import
    try:
        __import__(name)
    except Exception as e:
        tb = traceback.format_exc()
        # Filter noise: only show those where traceback mentions numpy or a compiled extension crash
        failures.append((name, tb))
        print("="*80)
        print("FAILED IMPORT:", name)
        print("- Exception traceback (short):")
        print(tb)
        # try to give pip info
        try:
            info = subprocess.check_output([py, "-m", "pip", "show", name], stderr=subprocess.DEVNULL).decode()
            print("- pip show for", name, ":\n", info)
        except Exception:
            # sometimes pip show name differs from import name; try guess by scanning pip freeze for substring
            print("- pip show failed for import name; trying heuristics...")
            try:
                for r in reqs:
                    if name.lower() in r.lower():
                        print("  Possible match from pip freeze:", r)
            except Exception:
                pass

print("\nSUMMARY: %d import failures detected.\n" % len(failures))
if failures:
    print("Failed imports (name and a short snippet). For each failing package, consider upgrading the package or rebuilding from source.")
    for n,t in failures:
        print("-", n)
else:
    print("No import failures detected by this scan.")

print("\nAlso listing any installed packages that are known to embed compiled extensions often linked to NumPy:")
common = ["scipy","scikit-learn","pandas","numba","faiss","librosa","tensorflow","torch","mxnet","skimage","opencv-python","xgboost"]
for c in common:
    try:
        out = subprocess.check_output([py,"-m","pip","show",c], stderr=subprocess.DEVNULL).decode()
        if out:
            print("\nPackage:", c)
            print(out)
    except Exception:
        pass

PY

python3 /tmp/find_numpy_offenders.py 2>&1 | tee /tmp/find_numpy_offenders.log
echo "Diagnostic saved to /tmp/find_numpy_offenders.log"
