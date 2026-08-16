"""Environment verification script for Kaggriculture."""
import sys
import platform
import os

# Ensure UTF-8 output where possible
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

print("=" * 60)
print("Verifying Kaggriculture Python Environment")
print("=" * 60)
print(f"Python executable : {sys.executable}")
print(f"Python version    : {platform.python_version()}")
print(f"Platform          : {platform.platform()}")
print("-" * 60)

packages = [
    ("kaggle_environments", "Kaggle Environments"),
    ("kaggle", "Kaggle API CLI"),
    ("gymnasium", "Gymnasium"),
    ("numpy", "NumPy"),
    ("pandas", "Pandas"),
    ("scipy", "SciPy"),
    ("sklearn", "Scikit-Learn"),
    ("torch", "PyTorch"),
    ("matplotlib", "Matplotlib"),
    ("ipykernel", "IPython Kernel"),
    ("tqdm", "TQDM"),
]

all_passed = True

for module_name, display_name in packages:
    try:
        mod = __import__(module_name)
        ver = getattr(mod, "__version__", "available")
        print(f"[OK]   {display_name:<20} : {ver}")
    except ImportError as e:
        print(f"[FAIL] {display_name:<20} : FAILED to import ({e})")
        all_passed = False

print("-" * 60)

# Check Kaggle Environments capabilities
try:
    import kaggle_environments
    envs = list(kaggle_environments.environments.keys())
    print(f"Registered kaggle-environments: {len(envs)} environments available")
    print(f"Sample envs: {envs[:10]}")
    if "kaggriculture" in envs:
        print("[OK]   kaggriculture is registered in kaggle_environments!")
    else:
        print("[INFO] kaggriculture environment will be loaded directly or via local package")
except Exception as e:
    print(f"kaggle-environments check note: {e}")

# Check PyTorch device
try:
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"PyTorch Device Available : {device}")
    if torch.cuda.is_available():
        print(f"CUDA Device Name        : {torch.cuda.get_device_name(0)}")
except Exception as e:
    print(f"Torch check note: {e}")

print("=" * 60)
if all_passed:
    print("ALL ENVIRONMENT CHECKS PASSED SUCCESSFULLY!")
else:
    print("SOME CHECKS FAILED. Please review the output above.")
print("=" * 60)
