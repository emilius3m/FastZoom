#!/usr/bin/env python3
"""
Poetry Configuration Validator
Validates and fixes common pyproject.toml issues
"""

import os
import sys
import re
from pathlib import Path

def validate_pyproject_toml():
    """Validate pyproject.toml file"""
    print("🔍 Validating pyproject.toml...")

    if not os.path.exists("pyproject.toml"):
        print("❌ pyproject.toml not found!")
        return False

    try:
        with open("pyproject.toml", "r", encoding="utf-8") as f:
            content = f.read()

        issues = []

        # Check for common issues

        # 1. Check Python version format
        python_match = re.search(r'python = ["\']([^"\']+)["\']', content)
        if python_match:
            python_version = python_match.group(1)
            if python_version == "3.13.7":
                issues.append(f"❌ Python version '{python_version}' is too specific. Use '^3.12' instead.")
            elif not re.match(r'^\^?\d+\.\d+$', python_version):
                issues.append(f"❌ Python version format '{python_version}' is invalid.")

        # 2. Check authors format
        authors_match = re.search(r'authors = \[([^\]]+)\]', content)
        if authors_match:
            authors_content = authors_match.group(1)
            if '"e3m"' in authors_content or "'e3m'" in authors_content:
                issues.append("❌ Author format should be 'Name <email@domain.com>' not just 'e3m'")

        # 3. Check for missing dependencies
        required_deps = [
            "fastapi", "sqlalchemy", "alembic", "uvicorn",
            "pydantic", "jinja2", "python-multipart", "pillow"
        ]

        for dep in required_deps:
            if f'"{dep}"' not in content and f"'{dep}'" not in content:
                # Check if it's in the format dep = "version"
                if not re.search(rf'^{re.escape(dep)}\s*=', content, re.MULTILINE):
                    issues.append(f"⚠️  Dependency '{dep}' might be missing")

        # 4. Check for conflicting Python versions in ruff config
        if 'target-version = "py312"' in content:
            python_constraint = re.search(r'python = ["\']([^"\']+)["\']', content)
            if python_constraint and '3.13' in python_constraint.group(1):
                issues.append("❌ Python version conflict: main constraint uses 3.13 but ruff targets 3.12")

        if issues:
            print("❌ Issues found in pyproject.toml:")
            for issue in issues:
                print(f"   {issue}")
            return False
        else:
            print("✅ pyproject.toml validation passed!")
            return True

    except Exception as e:
        print(f"❌ Error reading pyproject.toml: {e}")
        return False

def fix_common_issues():
    """Attempt to fix common pyproject.toml issues"""
    print("🔧 Attempting to fix common issues...")

    if not os.path.exists("pyproject.toml"):
        print("❌ pyproject.toml not found!")
        return False

    try:
        with open("pyproject.toml", "r", encoding="utf-8") as f:
            content = f.read()

        original_content = content

        # Fix 1: Python version too specific
        content = re.sub(
            r'python = "3\.13\.7"',
            'python = "^3.12"',
            content
        )

        # Fix 2: Author format
        content = re.sub(
            r'authors = \["e3m"\]',
            'authors = ["Archaeological Team <info@archeologico.it>"]',
            content
        )

        # Fix 3: Python version in ruff config
        content = re.sub(
            r'target-version = "py312"',
            'target-version = "python3.12"',
            content
        )

        # Fix 4: Add missing dependencies
        missing_deps = [
            'bcrypt = "^4.0.1"',
            'python-dotenv = "^1.0.0"'
        ]

        # Check if these are already present
        for dep in missing_deps:
            dep_name = dep.split(' = ')[0]
            if dep_name not in content:
                # Add to main dependencies section
                content = re.sub(
                    r'(jsonschema = "\^4\.23\.0"\n)',
                    rf'\1{dep}\n',
                    content
                )

        if content != original_content:
            with open("pyproject.toml", "w", encoding="utf-8") as f:
                f.write(content)
            print("✅ Fixed issues in pyproject.toml")
            return True
        else:
            print("ℹ️ No fixes needed")
            return True

    except Exception as e:
        print(f"❌ Error fixing pyproject.toml: {e}")
        return False

def main():
    print("🏺 Poetry Configuration Validator")
    print("=" * 40)

    if not validate_pyproject_toml():
        print("\n🔧 Attempting to fix issues...")
        if fix_common_issues():
            print("\n🔍 Revalidating after fixes...")
            if validate_pyproject_toml():
                print("\n🎉 pyproject.toml is now valid!")
                print("\nNext steps:")
                print("1. Run: poetry install")
                print("2. Run: poetry check")
                print("3. Run: poetry run uvicorn app.app:app --reload")
            else:
                print("\n❌ Still having issues. Consider using the installation script:")
                print("   .\\install.bat")
        else:
            print("\n❌ Could not fix issues automatically.")
            print("💡 Try using the installation script instead:")
            print("   .\\install.bat")
    else:
        print("\n🎉 pyproject.toml is valid!")
        print("🚀 You can now run:")
        print("   poetry install")
        print("   poetry run uvicorn app.app:app --reload")

if __name__ == "__main__":
    main()