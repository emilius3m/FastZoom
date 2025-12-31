"""
Script to merge refactored US endpoints with original us.py file.
This preserves USM endpoints and other functionality while updating US endpoints.
"""

import re

# Read the original file
with open('app/routes/api/v1/us.py', 'r', encoding='utf-8') as f:
    original_content = f.read()

# Find the USM section start (after US delete endpoint)
usm_section_marker = "# ------- USM CRUD - V1 ENDPOINTS -------"
usm_start_idx = original_content.find(usm_section_marker)

if usm_start_idx == -1:
    print("ERROR: Could not find USM section marker")
    exit(1)

# Extract USM and remaining content
usm_and_rest = original_content[usm_start_idx:]

# Read the refactored US endpoints
with open('app/routes/api/v1/us_refactored_part1.py', 'r', encoding='utf-8') as f:
    refactored_content = f.read()

# Remove the placeholder comment from refactored content
refactored_content = refactored_content.replace(
    "# NOTE: USM endpoints follow similar pattern - delegating to US Service\n" +
    "# Keeping the rest of the file temporarily for USM endpoints and bulk operations\n" +
    "# These will be refactored in the next step\n",
    ""
)

# Combine refactored US endpoints with original USM section
final_content = refactored_content.rstrip() + "\n\n" + usm_and_rest

# Write the merged file
with open('app/routes/api/v1/us.py', 'w', encoding='utf-8') as f:
    f.write(final_content)

print("✅ Successfully merged refactored US endpoints with original USM section")
print(f"📝 Refactored content length: {len(refactored_content)} chars")
print(f"📝 USM section length: {len(usm_and_rest)} chars")
print(f"📝 Final file length: {len(final_content)} chars")
