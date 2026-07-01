import re
path = 'D:/Nexabuild/forge/templates/index.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

target = "selectCategory(chip.innerText.replace(/^[^\w]*/, '').trim(), chip);"
replacement = "selectCategory(chip.innerText.replace(/^[^\w]*/, '').trim(), chip, true);"

content = content.replace(target, replacement)
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("done")
