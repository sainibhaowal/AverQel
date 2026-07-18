with open("/tmp/averqel_test/2312.txt", encoding="utf-8") as f:
    text = f.read()

# Find the section header "4.5"
import re

match = re.search(r"\n4\.5\s+[A-Za-z]+.*?\n", text)
if match:
    start = match.start()
    print("FOUND SECTION 4.5:")
    print(text[start : start + 3000])
else:
    print("Section 4.5 not found via strict regex.")
