iterations = 10_000_000
state = 1
total = 0

for _ in range(iterations):
    state = (1_103_515_245 * state + 12_345) & 0xFFFFFFFF
    if state & 0x80000000:
        total += 1
    else:
        total -= 1

print(total)
