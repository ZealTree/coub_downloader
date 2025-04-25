import re

def bump_version(version):
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise ValueError("Invalid version format. Expected X.Y.Z")
    
    major, minor, patch = map(int, match.groups())
    patch += 1
    return f"{major}.{minor}.{patch}"

def main():
    with open("version.txt", "r", encoding="utf-8") as f:
        current_version = f.read().strip()
    
    new_version = bump_version(current_version)
    
    with open("version.txt", "w", encoding="utf-8") as f:
        f.write(new_version + "\n")
    
    print(f"Version bumped from {current_version} to {new_version}")

if __name__ == "__main__":
    main()