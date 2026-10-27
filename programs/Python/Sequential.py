values = [float(index) for index in range(65536)]
total_sum = 0.0
for _ in range(256):
    for value in values:
        total_sum += value

print(total_sum)