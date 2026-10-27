iterations = 10_000_000
total = 0

for index in range(iterations):
    if index & 63:
        total += 1
    else:
        total -= 1

print(total)
