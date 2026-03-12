import re
import os

filepath = r"c:\Users\E3M\OneDrive - beniculturali.it\Desktop\FastZoom\app\templates\pages\tma\index.html"
with open(filepath, 'r', encoding='utf-8') as f:
    text = f.read()

# Replace input styles (normal inputs)
old_input = r'class="w-full border border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-white rounded bg-white px-3 py-2 focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none"'
new_input = r'class="w-full border-2 border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"'
text = text.replace(old_input, new_input)

# Replace readonly inputs
old_readonly = r'class="w-full border border-gray-300 dark:border-gray-600 dark:text-gray-400 rounded bg-gray-50 dark:bg-gray-700 px-3 py-2 outline-none"'
new_readonly = r'class="w-full border-2 border-gray-300 dark:border-gray-600 dark:bg-gray-600 bg-gray-100 dark:text-gray-400 rounded-lg px-4 py-2 outline-none cursor-not-allowed"'
text = text.replace(old_readonly, new_readonly)

# Replace labels structure
# Old: <label class="block"><span class="text-sm"><span class="text-xs font-mono bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 px-1 rounded mr-2">TSK</span>Tipo Scheda<span class="text-red-500 ml-1">*</span></span><input ...></label>
# We want to change the inner span to: <span class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">TSK - Tipo Scheda <span class="text-red-500">*</span></span>

# Regex to match the label content
pattern1 = r'<span class="text-sm"><span class="text-xs font-mono bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 px-1 rounded mr-2">(.*?)</span>(.*?)(<span class="text-red-500 ml-1">\*</span>)?</span>'

def repl1(m):
    code = m.group(1).strip()
    desc = m.group(2).strip()
    req = m.group(3) if m.group(3) else ""
    return f'<span class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">{code} - {desc} {req}</span>'

text = re.sub(pattern1, repl1, text)

# Match div versions (like CMPN) without the outer <label>
pattern2 = r'<div class="text-sm mb-[12]"><span class="text-xs font-mono bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 px-1 rounded mr-2">(.*?)</span>(.*?)(<span class="text-red-500 ml-1">\*</span>)?</div>'

def repl2(m):
    code = m.group(1).strip()
    desc = m.group(2).strip()
    req = m.group(3) if m.group(3) else ""
    return f'<div class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">{code} - {desc} {req}</div>'

text = re.sub(pattern2, repl2, text)

# Replace button styling for "+ Aggiungi..." buttons
old_btn = r'class="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded text-sm hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"'
new_btn = r'class="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm font-medium hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-blue-600 dark:text-blue-400"'
text = text.replace(old_btn, new_btn)

# Make sure outermost labels don't get the old styling
text = text.replace('<label>', '<label class="block">')
text = text.replace('<label class="block">', '<div class="block">')
text = text.replace('</label>', '</div>')
text = text.replace('<label class="block md:w-1/3">', '<div class="block md:w-1/3">')
# Fix radio/checkbox labels
text = text.replace('<div class="text-sm flex items-center gap-2">', '<label class="text-sm flex items-center gap-2 cursor-pointer">')
text = text.replace('<div class="flex items-center gap-4">', '<div class="flex items-center gap-6">')

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(text)

print("Formatting complete")
