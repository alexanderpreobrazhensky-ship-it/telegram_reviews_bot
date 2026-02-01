import subprocess
import sys


def main() -> int:
    result = subprocess.run([sys.executable, "-m", "pytest", "-q"])
    if result.returncode == 0:
        print("SELFTEST: PASS")
        return 0
    print("SELFTEST: FAIL")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
